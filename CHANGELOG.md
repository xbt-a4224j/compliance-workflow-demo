# [1.8.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.7.0...v1.8.0) (2026-04-19)


### Bug Fixes

* **router:** omit deprecated 'temperature' for Opus 4.x models ([4beef30](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/4beef3035afc1f0142bfac5999312048dc371acb))


### Features

* **ingest:** pypdf parser + tiktoken chunker with page-stamped DocChunks ([59cd268](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/59cd268177d6436b83cf285bd0db0b254dfc1e33))
* **rules+executor:** five FINRA-2210 rules + prompt tuning + hallucination guard ([4715f48](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/4715f4832ec5ea39d2e8e5c46491278c8b1800b0))

# [1.7.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.6.0...v1.7.0) (2026-04-19)


### Features

* **db:** postgres persistence + content-addressed findings cache ([a62a9f4](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/a62a9f470f6bc64b899595474b947d4ad24a85b5)), closes [#11](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/11)

# [1.6.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.5.0...v1.6.0) (2026-04-19)


### Features

* **executor:** orchestrator fans out leaves and aggregates with degraded semantics ([ce72159](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/ce72159a690278982e313ca0210743409ad3f47b)), closes [#6](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/6) [#17](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/17) [#17](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/17)

# [1.5.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.4.0...v1.5.0) (2026-04-19)


### Features

* **executor:** atomic check via router with page-stamped evidence ([aa8679d](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/aa8679d21fdef72e36f5c58562b6492a2d54ba30)), closes [#15](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/15)

# [1.4.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.3.0...v1.4.0) (2026-04-19)


### Features

* **dsl:** compile rules into content-addressed atomic-check DAG ([2445730](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/244573005af29747fdd993fb6a54e117dd2b4b35)), closes [#12](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/12)
* **router:** add retry, circuit breaker, and failover orchestrator ([c1bc2ea](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/c1bc2ea490f620dc3eda1dce4ce29174d5dc30c3))

# [1.3.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.2.0...v1.3.0) (2026-04-19)


### Features

* **router:** add anthropic, openai, and mock provider adapters ([8fdefcb](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/8fdefcbdc7e921d4444241f6ad42d182f19fb18d)), closes [#9](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/9)

# [1.2.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.1.0...v1.2.0) (2026-04-18)


### Features

* **dsl:** add pydantic v2 rule schema with 5 ops ([3d5cee1](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/3d5cee1bca92d7c9adecfd9c21bac3bd6f9df681)), closes [#6](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/6)

# [1.1.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.0.0...v1.1.0) (2026-04-18)


### Features

* **obs:** wire OpenTelemetry tracing with OTLP export and smoke check ([dce641e](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/dce641e76a1b0574475a1d66bf79386b3353316f))

# 1.0.0 (2026-04-18)


### Bug Fixes

* **ci:** drop removed python-version input from setup-uv and pin cache glob ([006e96f](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/006e96fbbf77e09ee8fbf48f2d3033773f09630a))
