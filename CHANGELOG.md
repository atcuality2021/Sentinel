# Changelog

All notable changes to this project are documented here. Format mirrors [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

- feat(memory): auto-reconcile contradicting findings to one live head per entity+topic
  (SENTINEL-021). `MemoryStore.write` now resolves a same-topic conflict at write time via a pure,
  deterministic policy (`_pick_winner`: newer → PRIVATE>PUBLIC → SM-2 strength/access → stable id),
  quarantining the loser with a new `superseded_by` link so `recall()` never serves both sides. Adds
  `reconcile_open_conflicts()` (backlog curator with golden-question rollback) and a cadence entry
  point `python -m sentinel.memory.curator`. The account page surfaces an "N superseded" count
  (no silent drops).
- (next change goes here)

## [0.1.0] - YYYY-MM-DD

- feat: initial repo bootstrap (BILTIQ-000)
