---
name: cma
description: >
  Pull a comparative market analysis when someone types /cma plus a street
  address, including in the grokbot Slack channel. The address can be glued
  to the command, for example /cma428 Lawnview Ave, New Castle, Pennsylvania 16105.
  Returns 4-5 sold and active comps within 1 mile. Use when the user runs /cma
  or asks for comps, a CMA, or a market analysis for a specific address.
user-invocable: true
argument-hint: "[address]"
---

# CMA

Run this when a message is a `/cma` command. The address may be glued to the
command (`/cma428 Lawnview Ave, New Castle, Pennsylvania 16105`), or written
as `/cma 428 Lawnview Ave, New Castle, Pennsylvania 16105`.

## Steps

1. Treat the text after `/cma` as one US street address. Do not ask a follow-up
   if the number, street, city, and state are already there.
2. From this repo, run:

   ```bash
   PYTHONPATH=src python -m cma "/cma428 Lawnview Ave, New Castle, Pennsylvania 16105"
   ```

   Pass the user's full message, including `/cma`.
3. Reply in the same Slack thread with the command's stdout, unchanged.
4. Do not add comps, prices, or property facts that are not in that output.
5. If the command exits non-zero, post its stdout as the reply.

## What the report contains

- The subject beds, baths, square footage, and year built when a listing or
  the Lawrence County assessment record has them
- A value band from the selected sold comps
- Up to 3 sold comps from the last 12 months and up to 2 homes on the market,
  five comps at most, all within 1 mile

The tool does not return owner names. Do not look up or post the owner.
Do not describe the neighborhood's people, schools, or safety. This is a
comp set, not an appraisal.
