# n 0.7 Unified Phased IR Package

This package is a reproducible design snapshot dated 2026-10-01.

## Status

- Design: accepted.
- Implementation: complete for the Windows x86-64/SSE2 `f64 add_scalar` native slice.
- Current executable baseline: n 0.7 phased native vertical slice with a 0.50 compatibility projection.
- Current verified n test baseline: 44 tests pass twice on the packaging host.
- Python bytecode compilation: passes on the packaging host.

The package does not claim general SSA/CFG, arena structural sharing, GPU/NPU/CXL
execution, self-hosting, or broad performance superiority. The authoritative native
path is `semantic -> planned -> machine`; `LIRKernel` remains a compatibility
projection whose machine code is checked against the new path.

## Start Here

1. `README.md` for the current project status.
2. `docs/superpowers/specs/2026-10-01-n-0.7-unified-phased-ir-design.md` for the accepted design.
3. `docs/superpowers/plans/2026-10-01-n-0.7-unified-phased-ir.md` for the TDD migration plan.
4. `N_DESIGN.md` section 21 for integration with the full language design.
5. `N_DESIGN_AUDIT.md` for open risks and evidence boundaries.

## Package Scope

Included are n source, current n tests and examples, core tl source, tl bootstrap
and regression entry points, current design/audit documents, and implementation
plans. Temporary diagnostics, Python caches, large trace dumps, prior archives,
and build-only symbol files are excluded.

`PACKAGE_MANIFEST.sha256` contains one SHA-256 entry for every packaged file except
itself. The archive digest is written beside the ZIP as
`n_0.7_unified_phased_ir_implemented.zip.sha256`.
