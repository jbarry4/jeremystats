"""
Filename: VOS_report_parser.py
Description: Parses a VOS cage-card report PDF into a per-mouse CSV.

Cards are located by their printed border rectangle rather than by the
external-ID text that used to head each card. That token is site/protocol
specific and has already changed once (X0-145 -> X6-041), which silently
broke card splitting; the border geometry is identical across every export
we have, old and new.

Two card layouts are handled:
  CENSUS  - 'Census <date> Sex <sex>' / 'Strain ...' / 'Code DOB ...'
            Notes list the parent cross plus one line per animal in the cage.
  BREEDER - '# Animals N' / 'M DOB .. F DOB ..' / 'Breeding Date ..' /
            'M Strain (ID) ..' / 'F Strain (ID) ..'
            The animals in the cage are the two parents, so a row is emitted
            for each of them (previously these produced a single ID-0 row).

Every card is checked against its own '# Animals' count; mismatches are
written to the debug log instead of failing silently.

Usage:
    python VOS_report_parser.py                        # newest 'VOS Report *.pdf' beside this script
    python VOS_report_parser.py "VOS Report 072826.pdf"
    python VOS_report_parser.py report.pdf -o out.csv --debug-dir "Debug/2026-07-28"
"""

import argparse
import csv
import os
import re
import sys

import pdfplumber

# --- CARD GEOMETRY ---------------------------------------------------------
# Outer border of a cage card is ~360pt wide and ~216pt tall on a 612x792 page.
MIN_CARD_WIDTH = 250
MIN_CARD_HEIGHT = 120

# --- PATTERNS --------------------------------------------------------------
# The separator between the ref and the cage card is U+2022, but stay
# permissive in case the export ever switches glyphs.
SEP = r'[^\w\s]'

RE_EXTERNAL_ID   = re.compile(r'^(\S+)\s+Species\b', re.M)
RE_NUM_ANIMALS   = re.compile(r'#\s*Animals\s+(\d+)')
RE_CENSUS        = re.compile(r'\bCensus\s+(\S+)')
RE_SEX           = re.compile(r'\bSex\s+([A-Za-z]+)')
RE_CAGE_CARD     = re.compile(r'\b(CC-\d+(?:-\d+)?)\b')
RE_BREEDING_DATE = re.compile(r'\bBreeding Date\s+(\S+)')
RE_CREATED       = re.compile(r'\bCreated\s+(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)')
RE_REF           = re.compile(r'\bCreated\s+\S+\s+\S+\s+([A-Za-z]+-\d+)\s*' + SEP + r'\s*CC-')
RE_NOTES         = re.compile(r'^Notes\b[ \t]*(.*?)(?=^Created\s)', re.M | re.S)
RE_NOTES_TAIL    = re.compile(r'^Notes\b[ \t]*(.*)\Z', re.M | re.S)

# 'M Strain (ID) 1602 Kcnt1-YH;SST' -- the numeric ID is absent in older exports
RE_PARENT_STRAIN = re.compile(r'^([MF])\s+Strain\s*\(ID\)\s*(?:(\d{3,4})\b\s*)?(.*)$')
# 'P.I. Barry J. M DOB 04/18/26 F DOB 04/18/26'  (either value may be blank)
RE_M_DOB         = re.compile(r'\bM\s+DOB\s+(\d[\d/\-]*)')
RE_F_DOB         = re.compile(r'\bF\s+DOB\s+(\d[\d/\-]*)')
RE_ANY_M_DOB     = re.compile(r'\bM\s+DOB\b')
RE_CODE_DOB      = re.compile(r'\bDOB\s+(\d[\d/\-]*)')

# A parent cross: 508x505 / 328x 313 / 329 (M) x 302 (F) / 541(M)x320(F)
RE_CROSS = re.compile(
    r'(?P<m>\d{3,4})\s*(?:\((?P<msex>[MF])\))?\s*(?:\(previously\s+(?P<mprev>\d{3,4})\)\s*)?'
    r'[xX]\s*'
    r'(?P<f>\d{3,4})\s*(?:\((?P<fsex>[MF])\))?\s*(?:\(previously\s+(?P<fprev>\d{3,4})\))?',
    re.I,
)
# Closing parens are optional: notes are hand-typed and '576 (previously 533'
# (no closing paren) occurs in real exports.
RE_PREVIOUSLY = re.compile(r'\(\s*previously\s+(\d{3,4})\s*\)?', re.I)
RE_PARENS     = re.compile(r'\([^)]*(?:\)|$)')
RE_ID         = re.compile(r'\b(\d{3,4})\b')

SEX_NORMAL = {'M': 'MALE', 'MALE': 'MALE', 'F': 'FEMALE', 'FEMALE': 'FEMALE'}


# --- CARD EXTRACTION -------------------------------------------------------

def find_card_boxes(page):
    """Return the bounding box of each cage card on the page, top to bottom."""
    boxes = []
    for r in page.rects:
        w = r['x1'] - r['x0']
        h = r['bottom'] - r['top']
        if w >= MIN_CARD_WIDTH and h >= MIN_CARD_HEIGHT:
            boxes.append((round(r['x0'], 1), round(r['top'], 1),
                          round(r['x1'], 1), round(r['bottom'], 1)))

    # Each card draws an outer border and a slightly inset one; keep the outer.
    boxes = sorted(set(boxes), key=lambda b: (b[1], b[0]))
    kept = []
    for box in boxes:
        x0, top, x1, bottom = box
        if any(k[0] <= x0 and k[1] <= top and k[2] >= x1 and k[3] >= bottom for k in kept):
            continue
        kept.append(box)
    return kept


def split_page_by_footer(text):
    """Fallback card split for pages with no border rectangles.

    Every card ends with 'Created <when> [<ref>] * CC-##### * External ID:'.
    """
    footer = re.compile(r'Created\s+.*?' + SEP + r'\s*CC-\d+(?:-\d+)?\s*' + SEP + r'\s*External ID:')
    cards, start = [], 0
    for m in footer.finditer(text):
        chunk = text[start:m.end()].strip()
        if chunk:
            cards.append(chunk)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        cards.append(tail)
    return cards


def get_card_texts(page):
    """Return (list_of_card_texts, method_used) for one page."""
    boxes = find_card_boxes(page)
    if boxes:
        out = []
        for box in boxes:
            txt = (page.crop(box).extract_text() or '').strip()
            if txt:
                out.append(txt)
        if out:
            return out, 'rect'
    return split_page_by_footer(page.extract_text() or ''), 'footer'


# --- NOTES / ID PARSING ----------------------------------------------------

def get_notes(card_text):
    m = RE_NOTES.search(card_text) or RE_NOTES_TAIL.search(card_text)
    return m.group(1).strip() if m else ''


def is_cross_line(line):
    """True if the line records the parent pairing rather than an animal."""
    if RE_CROSS.search(line):
        return True
    return line.strip().lower().rstrip(':') in ('parents', 'parent')


def parse_animal_line(line):
    """Pull one animal off a notes line.

    Numbers inside parentheses are annotations, not tags -- '1608 (previously
    581)' is animal 1608, and '1635 (black coat)' is animal 1635.
    Returns (tag, previous_tag) or (None, '').
    """
    prev = RE_PREVIOUSLY.search(line)
    stripped = RE_PARENS.sub(' ', line)
    m = RE_ID.search(stripped)
    if not m:
        return None, ''
    return m.group(1), (prev.group(1) if prev else '')


def extract_census_animals(notes, warn):
    """Animals housed in a census cage: one per non-cross notes line."""
    animals = []
    for line in notes.split('\n'):
        if not line.strip() or is_cross_line(line):
            continue
        tag, prev = parse_animal_line(line)
        if tag is not None:
            animals.append({'tag': tag, 'prev': prev, 'sex': '', 'dob': '', 'strain': ''})
    if not animals:
        warn.append('no animal IDs found in notes')
    return animals


def extract_breeder_animals(card_text, notes, m_dob, f_dob, warn):
    """A breeding cage houses the pair itself, so emit a row per parent."""
    parents = {}
    for line in card_text.split('\n'):
        m = RE_PARENT_STRAIN.match(line.strip())
        if m:
            parents[m.group(1)] = {'tag': m.group(2) or '', 'strain': m.group(3).strip()}

    animals = []

    def add(side, tag, prev=''):
        animals.append({
            'tag': tag,
            'prev': prev,
            'sex': 'MALE' if side == 'M' else 'FEMALE',
            'dob': m_dob if side == 'M' else f_dob,
            'strain': parents.get(side, {}).get('strain', ''),
        })

    # Preferred source: the numeric IDs printed on the M/F Strain lines.
    if parents.get('M', {}).get('tag') or parents.get('F', {}).get('tag'):
        for side in ('M', 'F'):
            tag = parents.get(side, {}).get('tag')
            if tag:
                add(side, tag)
            else:
                warn.append(f'breeder card missing {side} Strain (ID) number')
        # Recover a renamed parent from the notes cross, e.g. '1607(M)(previously 586)'.
        cm = RE_CROSS.search(notes)
        if cm:
            for a in animals:
                if a['tag'] == cm.group('m') and cm.group('mprev'):
                    a['prev'] = cm.group('mprev')
                elif a['tag'] == cm.group('f') and cm.group('fprev'):
                    a['prev'] = cm.group('fprev')
        return animals

    # Older exports print no IDs on the strain lines; read the cross in the notes.
    cm = RE_CROSS.search(notes)
    if cm:
        left_sex = (cm.group('msex') or 'M').upper()
        right_sex = (cm.group('fsex') or 'F').upper()
        if not cm.group('msex') and not cm.group('fsex'):
            warn.append('cross has no (M)/(F) markers; assumed male x female')
        add(left_sex, cm.group('m'), cm.group('mprev') or '')
        add(right_sex, cm.group('f'), cm.group('fprev') or '')
        return animals

    # No pairing at all (e.g. a split cage holding a single former breeder).
    for line in notes.split('\n'):
        if not line.strip():
            continue
        tag, prev = parse_animal_line(line)
        if tag is not None:
            animals.append({'tag': tag, 'prev': prev, 'sex': '',
                            'dob': m_dob or f_dob, 'strain': ''})
    if not animals:
        warn.append('breeder card yielded no animal IDs')
    return animals


# --- CARD -> RECORDS -------------------------------------------------------

def parse_card(card_text, page_num, position):
    """Turn one card into a list of per-mouse record dicts."""
    warn = []
    lines = [l.rstrip() for l in card_text.split('\n')]
    flat = ' '.join(l.strip() for l in lines if l.strip())

    is_breeder = bool(RE_ANY_M_DOB.search(card_text)
                      or re.search(r'^\s*[MF]\s+Strain\s*\(ID\)', card_text, re.M)
                      or RE_BREEDING_DATE.search(card_text))

    ext = RE_EXTERNAL_ID.search(card_text)
    cage = RE_CAGE_CARD.search(card_text)
    declared_match = RE_NUM_ANIMALS.search(card_text)
    census = RE_CENSUS.search(card_text)
    created = RE_CREATED.search(card_text)
    ref = RE_REF.search(card_text)
    breeding_date = RE_BREEDING_DATE.search(card_text)
    notes = get_notes(card_text)

    if not cage:
        warn.append('no cage card number found')

    card_dob = card_sex = card_strain = ''
    m_dob = f_dob = ''

    if is_breeder:
        md, fd = RE_M_DOB.search(card_text), RE_F_DOB.search(card_text)
        m_dob = md.group(1) if md else ''
        f_dob = fd.group(1) if fd else ''
        card_dob = m_dob or f_dob
    else:
        for line in lines:
            if RE_PARENT_STRAIN.match(line.strip()):
                continue
            if not card_dob:
                d = RE_CODE_DOB.search(line)
                if d:
                    card_dob = d.group(1)
            if not card_strain:
                s = re.search(r'\bStrain\s+(.+)$', line)
                if s:
                    card_strain = s.group(1).strip()
        sx = RE_SEX.search(card_text)
        card_sex = sx.group(1) if sx else ''
        if not card_sex:
            warn.append('census card has no Sex')
        if not card_dob:
            warn.append('census card has no DOB')

    if is_breeder:
        animals = extract_breeder_animals(card_text, notes, m_dob, f_dob, warn)
    else:
        animals = extract_census_animals(notes, warn)

    declared = int(declared_match.group(1)) if declared_match else None
    if declared is not None and declared != len(animals):
        warn.append(f'found {len(animals)} IDs but card declares # Animals {declared}')

    base = {
        'Card Type': 'BREEDER' if is_breeder else 'CENSUS',
        'External ID': ext.group(1) if ext else '',
        'Cage Card': cage.group(1) if cage else '',
        'Strain': card_strain,
        'DOB': card_dob,
        'Sex': card_sex,
        'Notes': ' | '.join(l.strip() for l in notes.split('\n') if l.strip()),
        'Census Date': census.group(1) if census else '',
        'Breeding Date': breeding_date.group(1) if breeding_date else '',
        '# Animals': declared if declared is not None else '',
        'Created': created.group(1) if created else '',
        'Ref': ref.group(1) if ref else '',
        'Source Page': page_num,
        'Position on Page': position,
        'Mice In Card': len(animals),
        'ID Count Matches # Animals': ('' if declared is None
                                       else ('YES' if declared == len(animals) else 'NO')),
        'Parse Warnings': '; '.join(warn),
        'Raw Card Text': flat,
    }

    if not animals:
        rec = dict(base)
        rec.update({'Extracted Sorting ID': 0, 'Mouse Tag': '', 'Previous Tag': '',
                    'Sex Normalized': SEX_NORMAL.get(card_sex.upper(), card_sex.upper())})
        return [rec], warn

    records = []
    for a in animals:
        rec = dict(base)
        sex = a['sex'] or card_sex
        rec.update({
            'Extracted Sorting ID': int(a['tag']),
            'Mouse Tag': a['tag'],
            'Previous Tag': a['prev'],
            'Sex': sex,
            'Sex Normalized': SEX_NORMAL.get(sex.upper(), sex.upper()),
            'DOB': a['dob'] or card_dob,
            'Strain': a['strain'] or card_strain,
        })
        records.append(rec)
    return records, warn


# --- DRIVER ----------------------------------------------------------------

def build_column_map(stamp):
    """Original nine columns keep their names/order; diagnostics are appended."""
    suffix = f' {stamp}' if stamp else ''
    return [
        ('Extracted Sorting ID', f'Extracted Sorting ID{suffix}'),
        ('Cage Card',            f'Cage Card{suffix}'),
        ('DOB',                  f'DOB{suffix}'),
        ('Sex',                  f'Sex{suffix}'),
        ('Strain',               'Strain'),
        ('Notes',                'Notes'),
        ('Source Page',          'Source Page'),
        ('Position on Page',     'Position on Page'),
        ('Raw Card Text',        'Raw Card Text'),
        ('Card Type',            'Card Type'),
        ('External ID',          'External ID'),
        ('Census Date',          'Census Date'),
        ('Breeding Date',        'Breeding Date'),
        ('Sex Normalized',       'Sex Normalized'),
        ('Mouse Tag',            'Mouse Tag'),
        ('Previous Tag',         'Previous Tag'),
        ('# Animals',            '# Animals'),
        ('Mice In Card',         'Mice In Card'),
        ('ID Count Matches # Animals', 'ID Count Matches # Animals'),
        ('Created',              'Created'),
        ('Ref',                  'Ref'),
        ('Parse Warnings',       'Parse Warnings'),
    ]


def parse_pdf(pdf_path, debug_dir=None):
    records, log, card_dump, ext_ids = [], [], [], set()

    with pdfplumber.open(pdf_path) as pdf:
        log.append(f'PDF: {pdf_path}')
        log.append(f'Pages: {len(pdf.pages)}')
        total_cards = 0

        for page_num, page in enumerate(pdf.pages, start=1):
            card_texts, how = get_card_texts(page)
            if not card_texts:
                log.append(f'[WARN] page {page_num}: no cards detected')
                continue
            log.append(f'page {page_num}: {len(card_texts)} card(s) via {how}')
            total_cards += len(card_texts)

            for pos, card_text in enumerate(card_texts, start=1):
                recs, warn = parse_card(card_text, page_num, pos)
                records.extend(recs)
                if recs[0]['External ID']:
                    ext_ids.add(recs[0]['External ID'])
                card_dump.append(
                    f'\n{"=" * 90}\nPAGE {page_num} CARD {pos}  '
                    f'[{recs[0]["Card Type"]}] {recs[0]["Cage Card"]}\n{"=" * 90}\n'
                    f'{card_text}\n--- parsed -> {len(recs)} row(s): '
                    f'{[r["Extracted Sorting ID"] for r in recs]}\n'
                )
                for w in warn:
                    line = f'[WARN] page {page_num} card {pos} ({recs[0]["Cage Card"]}): {w}'
                    log.append(line)
                    card_dump.append(line + '\n')

    log.append(f'Total cards: {total_cards}')
    log.append(f'Total mouse rows: {len(records)}')
    log.append(f'External IDs seen: {sorted(ext_ids)}')
    log.append(f'Rows with warnings: {len([r for r in records if r["Parse Warnings"]])}')

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        with open(os.path.join(debug_dir, f'{base}__parse_log.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(log) + '\n')
        with open(os.path.join(debug_dir, f'{base}__cards.txt'), 'w', encoding='utf-8') as f:
            f.writelines(card_dump)

    for line in log:
        print(line)
    return records


def newest_report(folder):
    pdfs = [os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().startswith('vos report') and f.lower().endswith('.pdf')]
    return max(pdfs, key=os.path.getmtime) if pdfs else None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='Parse a VOS cage-card report PDF into a per-mouse CSV.')
    ap.add_argument('pdf', nargs='?',
                    help='input PDF (default: newest "VOS Report *.pdf" beside this script)')
    ap.add_argument('-o', '--output', help='output CSV (default: same name as the PDF)')
    ap.add_argument('--debug-dir', help='write parse log and per-card text dump here')
    args = ap.parse_args()

    pdf_path = args.pdf or newest_report(here)
    if not pdf_path:
        sys.exit('[ERROR] No "VOS Report *.pdf" found next to this script.')
    if not os.path.exists(pdf_path):
        pdf_path = os.path.join(here, pdf_path)
    if not os.path.exists(pdf_path):
        sys.exit(f'[ERROR] PDF not found: {args.pdf}')

    out_csv = args.output or os.path.splitext(pdf_path)[0] + '.csv'
    if not os.path.isabs(out_csv):
        out_csv = os.path.join(here, out_csv)

    stamp_match = re.search(r'\d{6}', os.path.basename(pdf_path))
    stamp = stamp_match.group() if stamp_match else ''

    print(f'[STATUS] Opening PDF: {pdf_path}')
    records = parse_pdf(pdf_path, args.debug_dir)
    if not records:
        sys.exit('[ERROR] No records parsed.')

    records.sort(key=lambda r: (r['Extracted Sorting ID'], r['Source Page'], r['Position on Page']))

    column_map = build_column_map(stamp)
    print(f'[STATUS] Writing {len(records)} rows to {out_csv}')
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[new for _, new in column_map])
        writer.writeheader()
        for rec in records:
            writer.writerow({new: rec.get(orig, '') for orig, new in column_map})

    bad = [r for r in records if r['ID Count Matches # Animals'] == 'NO']
    if bad:
        print(f'[REVIEW] {len(bad)} row(s) whose card ID count disagrees with "# Animals" '
              f'-- see the "Parse Warnings" column.')
    print('[SUCCESS] Done.')


if __name__ == '__main__':
    main()
