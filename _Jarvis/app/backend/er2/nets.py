"""Two small set networks, in numpy (no GPU stack needed here or on the VACC).

A mouse is a bag of events. Each event goes through the same two layers
(phi); the bag is pooled into one vector -- the plain mean ("deep sets",
Zaheer et al. 2017) or a learned weighting ("attention pooling", Ilse et al.
2018) -- and a small head makes the mouse's call. The call is never made per
event: the label belongs to the mouse.

    net = SetNet(n_in, kind="attention", task="binary")
    net.fit(X, bag, y)                 # X events x features, bag = mouse index per event
    p = net.predict(X_test, bag_test)  # one value per bag
    w = net.weights(X_test, bag_test)  # attention: each event's weight in its bag

Training: Adam, weight decay, input dropout, and each epoch a fresh sample of
at most `per_bag` events from every training mouse (so a mouse with 700
events does not outvote one with 70).
"""
import numpy as np


def _relu(x):
    return np.maximum(x, 0.0)


class SetNet(object):
    def __init__(self, n_in, kind="mean", task="binary", n_out=1, h1=64, h2=32, h3=16, att=16, lr=1e-3, wd=1e-4,
                 epochs=250, per_bag=128, drop=0.1, seed=0):
        self.kind, self.task, self.n_out = kind, task, (n_out if task == "multiclass" else 1)
        self.lr, self.wd, self.epochs, self.per_bag, self.drop = lr, wd, epochs, per_bag, drop
        rng = np.random.default_rng(seed)
        self.rng = rng

        def he(a, b):
            return (rng.standard_normal((a, b)) * np.sqrt(2.0 / a)).astype(np.float64)
        self.P = {"W1": he(n_in, h1), "b1": np.zeros(h1), "W2": he(h1, h2), "b2": np.zeros(h2),
                  "R1": he(h2, h3), "c1": np.zeros(h3), "R2": he(h3, self.n_out) * 0.1, "c2": np.zeros(self.n_out)}
        if kind == "attention":
            self.P["V"] = he(h2, att) * 0.5
            self.P["w"] = rng.standard_normal(att) * 0.1
        self.m = {k: np.zeros_like(v) for k, v in self.P.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.P.items()}
        self.t = 0

    # ------------------------------------------------------------ forward
    def _forward(self, X, starts, sizes):
        P = self.P
        A1 = X @ P["W1"] + P["b1"]
        H1 = _relu(A1)
        A2 = H1 @ P["W2"] + P["b2"]
        H2 = _relu(A2)
        cache = {"X": X, "A1": A1, "H1": H1, "A2": A2, "H2": H2}
        if self.kind == "attention":
            U = np.tanh(H2 @ P["V"])
            s = U @ P["w"]
            alpha = np.empty_like(s)
            for st, n in zip(starts, sizes):
                e = np.exp(s[st:st + n] - s[st:st + n].max())
                alpha[st:st + n] = e / e.sum()
            Z = np.add.reduceat(alpha[:, None] * H2, starts, axis=0)
            cache.update(U=U, alpha=alpha)
        else:
            Z = np.add.reduceat(H2, starts, axis=0) / sizes[:, None]
        G1 = Z @ P["R1"] + P["c1"]
        G = _relu(G1)
        out = G @ P["R2"] + P["c2"]
        cache.update(Z=Z, G1=G1, G=G)
        return out, cache

    def _loss_grad(self, out, y):
        n = out.shape[0]
        if self.task == "binary":
            p = 1.0 / (1.0 + np.exp(-out[:, 0]))
            return (p - y)[:, None] / n
        if self.task == "regression":
            return 2.0 * (out[:, 0] - y)[:, None] / n
        e = np.exp(out - out.max(axis=1, keepdims=True))
        pr = e / e.sum(axis=1, keepdims=True)
        Y = np.zeros_like(pr)
        Y[np.arange(n), y.astype(int)] = 1.0
        return (pr - Y) / n

    def _backward(self, d_out, cache, starts, sizes, bag_of_event):
        P, g = self.P, {}
        G, Z = cache["G"], cache["Z"]
        g["R2"] = G.T @ d_out
        g["c2"] = d_out.sum(axis=0)
        dG = d_out @ P["R2"].T
        dG1 = dG * (cache["G1"] > 0)
        g["R1"] = Z.T @ dG1
        g["c1"] = dG1.sum(axis=0)
        dZ = dG1 @ P["R1"].T
        H2 = cache["H2"]
        if self.kind == "attention":
            alpha, U = cache["alpha"], cache["U"]
            dZe = dZ[bag_of_event]
            dH2 = alpha[:, None] * dZe
            dalpha = (H2 * dZe).sum(axis=1)
            mean_da = np.add.reduceat(alpha * dalpha, starts)
            ds = alpha * (dalpha - mean_da[bag_of_event])
            g["w"] = U.T @ ds
            dpre = np.outer(ds, P["w"]) * (1.0 - U ** 2)
            g["V"] = H2.T @ dpre
            dH2 = dH2 + dpre @ P["V"].T
        else:
            dH2 = dZ[bag_of_event] / sizes[bag_of_event][:, None]
        dA2 = dH2 * (cache["A2"] > 0)
        g["W2"] = cache["H1"].T @ dA2
        g["b2"] = dA2.sum(axis=0)
        dA1 = (dA2 @ P["W2"].T) * (cache["A1"] > 0)
        g["W1"] = cache["X"].T @ dA1
        g["b1"] = dA1.sum(axis=0)
        return g

    def _adam(self, g, b1=0.9, b2=0.999, eps=1e-8):
        self.t += 1
        for k in self.P:
            gk = g[k] + (self.wd * self.P[k] if k in ("W1", "W2", "R1", "R2", "V") else 0.0)
            self.m[k] = b1 * self.m[k] + (1 - b1) * gk
            self.v[k] = b2 * self.v[k] + (1 - b2) * gk ** 2
            mh = self.m[k] / (1 - b1 ** self.t)
            vh = self.v[k] / (1 - b2 ** self.t)
            self.P[k] -= self.lr * mh / (np.sqrt(vh) + eps)

    @staticmethod
    def _bags(bag):
        """Events sorted by bag: (order, starts, sizes, bag id per sorted event, bag ids)."""
        order = np.argsort(bag, kind="stable")
        b = bag[order]
        ids, starts, sizes = np.unique(b, return_index=True, return_counts=True)
        return order, starts, sizes, np.repeat(np.arange(ids.size), sizes), ids

    # ------------------------------------------------------------ public
    def fit(self, X, bag, y_by_bag):
        """y_by_bag: {bag id: target}."""
        X = np.asarray(X, float)
        ids = np.array(sorted(y_by_bag))
        members = {b: np.where(bag == b)[0] for b in ids}
        y = np.array([y_by_bag[b] for b in ids], float)
        for _ in range(self.epochs):
            pick = []
            for b in ids:
                m = members[b]
                pick.append(m if m.size <= self.per_bag else self.rng.choice(m, self.per_bag, replace=False))
            sizes = np.array([p.size for p in pick])
            starts = np.r_[0, np.cumsum(sizes)[:-1]]
            Xb = X[np.concatenate(pick)]
            if self.drop:
                Xb = Xb * (self.rng.random(Xb.shape) > self.drop) / (1.0 - self.drop)
            out, cache = self._forward(Xb, starts, sizes)
            d = self._loss_grad(out, y)
            g = self._backward(d, cache, starts, sizes, np.repeat(np.arange(ids.size), sizes))
            self._adam(g)
        return self

    def predict(self, X, bag):
        order, starts, sizes, _bev, ids = self._bags(np.asarray(bag))
        out, _ = self._forward(np.asarray(X, float)[order], starts, sizes)
        if self.task == "binary":
            return ids, 1.0 / (1.0 + np.exp(-out[:, 0]))
        if self.task == "regression":
            return ids, out[:, 0]
        e = np.exp(out - out.max(axis=1, keepdims=True))
        return ids, e / e.sum(axis=1, keepdims=True)

    def weights(self, X, bag):
        """Attention: each event's weight within its bag (events in the input order)."""
        if self.kind != "attention":
            return None
        bag = np.asarray(bag)
        order, starts, sizes, _bev, ids = self._bags(bag)
        _, cache = self._forward(np.asarray(X, float)[order], starts, sizes)
        w = np.empty(bag.size)
        w[order] = cache["alpha"]
        return w
