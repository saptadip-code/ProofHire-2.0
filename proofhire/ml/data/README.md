# ProofHire synthetic dataset (`listings_synthetic.csv`)

**SYNTHETIC BENCHMARK DATA.** Every row is machine-generated from phrase banks with fictional company names and
invented salary medians. It is not real listing data and not verified salary data. Metrics measured on it are a
*synthetic benchmark*, never real-world accuracy.

## Provenance
- Command: `PYTHONPATH=backend python ml/data/generate_synthetic.py --n 6000 --risky-ratio 0.38 --seed 42 --out ml/data/listings_synthetic.csv`
- Seed: **42**
- Generator commit hash (at generation time): `unknown (not a git checkout when generated)`
- CSV sha256: `2638fa8fb9c33050e9d58d079e6789980002937f6155281fd37a26b334e58b8c`
- Never edit the CSV by hand; change the generator and re-run.

## Counts (actual, from this file)
- Rows: 6000; label=1 (risky): 2306 (38.43%); label=0 (legit): 3694
- Label-noise rows (label disagrees with scam_pattern): 120
- Splits: {'holdout': 228, 'test': 867, 'train': 4040, 'val': 865}
- scam_pattern: {'advance_fee': 684, 'data_harvest': 342, 'fake_offer_letter': 228, 'ghost_company': 342, 'legit': 3720, 'mlm_pyramid': 228, 'unrealistic_pay': 456}
- difficulty: {'easy': 5286, 'messy': 372, 'subtle': 342}

## Rules
- Risky mix 30/20/15/15/10/10 (advance_fee, unrealistic_pay, data_harvest, ghost_company, mlm_pyramid, fake_offer_letter).
- 15% of risky rows are `subtle`; 10% of legit rows are `messy`.
- 2% of labels are flipped at random (label noise). Flipped rows keep their original scam_pattern.
- Split: train 70 / val 15 / test 15, stratified by scam_pattern; all `fake_offer_letter` rows are `holdout` (never in train/val/test).
- Optional fields are empty strings on purpose; salary is 0 when not stated.

## Known limitations
- Generator and evidence rules share vocabulary, so synthetic scores will look high; use the pattern-holdout and the hand-written set for harder checks.
- Company names and phrase banks repeat across splits (small fictional vocabulary); only exact duplicate listings are prevented.
- Messy legit rows still have descriptions of at least 50 words (A3 column contract), so `vague_desc` is rarely/never set in this data.
