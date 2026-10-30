# Contributing to ARIADNE

Reproduce the current result before changing it: `make install`, `make data`,
`make test` and `make lint`. Use a focused feature branch and a pull request.

Each PR should explain the problem, changed behavior, actual verification and
remaining uncertainty. Ask a teammate to inspect at least two substantive aspects
such as a graph invariant, a split assumption, a failure case or a user journey.
Review comments must describe real observations and decisions.

Do not commit `.env`, access tokens, raw data, virtual environments or downloaded
model weights. Source and data licenses are different. Do not import `TREATS`
or `PALLIATES` into predictive evidence projections. Never add a hard-coded result
to improve a demonstration or report a test that did not execute.

AI assistance is disclosed in [docs/authorship.md](docs/authorship.md). Commit
authorship must describe who actually performed or accepted the work. Automated
agents do not count as separate human teammates.
