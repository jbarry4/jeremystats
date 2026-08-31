"""
Recursive fractal tree using Python's built-in turtle graphics.

Each branch splits into two smaller branches (left and right), and each of
those does the same thing again -- that's the recursion. The tree is
"self-similar": every branch looks like a smaller version of the whole tree.

Run it:  python fractal.py
"""

import turtle


def draw_branch(t, length, depth):
    # Base case: branches too small / too deep -- stop recursing.
    if depth == 0 or length < 5:
        return

    # Draw this branch.
    t.forward(length)

    # --- right sub-tree ---
    t.right(25)
    draw_branch(t, length * 0.7, depth - 1)   # recurse: smaller branch

    # --- left sub-tree ---
    t.left(50)                                # undo right turn, then go left
    draw_branch(t, length * 0.7, depth - 1)   # recurse: smaller branch

    # Restore heading and position so the caller continues cleanly.
    t.right(25)
    t.backward(length)


def main():
    screen = turtle.Screen()
    screen.title("Recursive Fractal Tree")
    screen.bgcolor("white")

    t = turtle.Turtle()
    t.speed(0)          # fastest drawing
    t.color("forestgreen")
    t.left(90)          # point the turtle upward
    t.penup()
    t.goto(0, -250)     # start near the bottom of the screen
    t.pendown()

    draw_branch(t, 120, depth=10)   # trunk length 120, 10 levels of recursion

    screen.exitonclick()   # click the window to close


if __name__ == "__main__":
    main()
