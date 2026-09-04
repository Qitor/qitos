# Self-contained documentation qualification

## Source identity and scope

Runtime/start: `60809b3be388d22ea40ea41b4aaa1f5540c76fda`.
Historical G5: `717b4cf1b23f2ed252cd03234ffd8605038d9567`; its historical
2663 passed / 50 skipped result is not reattributed to this task.
`qitos/`, package metadata/dependencies, public interface budgets and quality
allowances are unchanged. This is a documentation/example/testing change.

## Delivered

- Quickstart uses the generated notes project; all required files are on the page.
- Eight core learning units plus real-provider configuration, in EN and zh.
- Four navigation tabs, seven current core API categories, 45 unique imported
  API symbols, checked signatures/defaults/source links, extension index.
- Previous API text remains explicitly historical; old entry URLs remain reachable.
- Source-to-MDX synchronization and installed-wheel page extraction are CI gates.

## Local verification

Python 3.12.7; wheel built from unchanged runtime, SHA256
`2d7a46baf4d3831bb97c0657b200d9210989b00b12c1e113186a31790f850e44`.

- Combined requested docs/example/workflow/architecture/public-surface suites:
  **787 passed, 1 skipped** in 59.32 seconds. The skip is the explicit Docker opt-in.
- Separate Docker page extraction plus original installed golden paths,
  examples smoke and scaffold execution: **17 passed** in 52.63 seconds.
  Both EN/zh Docker pages execute private and explicitly published variants.
- Independent installed page suite: **20 passed, 1 skipped**; includes sequential
  learning in one project, generated-project install/test, qita HTTP replay and export.
- Final API/source drift check passed; changed Python static checks passed.
- Navigation/parity/links passed; **166 MDX pages compiled, 0 failures**.
- Real Mintlify preview: **46 changed routes at 1440px and 390px**, all HTTP 200,
  no page-level horizontal overflow. Reviewed desktop/mobile screenshots.
- Clipboard copied the exact 3703-character complete notes.py; API index link
  reached the intended composition symbol anchor. Code labels render correctly.
- `git diff --check` and frozen-runtime scope proof passed.

The JUnit evidence digest is `79b2c4899b4ffafe252a4d3951ab7f61f7465029b3f3becbe64eac75ba65cfa2`.
Evidence includes XML, command output, browser route receipts and screenshots;
public source identities and this digest are portable independently of local paths.

## Tooling and limits

Preview executed the isolated `@mintlify/cli` 4.0.1476 binary from the existing
locked documentation tool distribution (which also contains mint 4.2.873).
MDX compiler 3.1.1 and Playwright CLI 0.1.19. No global upgrade was performed.
Local Mintlify search requires login and was not activated; navigation, anchors,
code copy, page rendering and responsive layout were tested without credentials.

Handoff serializes transfer admission, source cleanup and destination execution.
Concurrent same-head destination restore/source callback owner conflict remains
explicitly documented with reproduction in the implementation plan. No runtime
fix or relaxed check is hidden in the example. Fake providers prove mechanisms,
not autonomous model success. Real-provider config validation sends no requests.

## Promotion

The implementation is submitted through a PR to master. Exact-head GitHub checks,
merge and live-site verification must be read from the PR and deployment evidence;
this local report does not claim those remote operations have already succeeded.
The concurrent V5 drafts in the main worktree are outside this change.
