# 1.0.0 (2026-04-19)


### Bug Fixes

* **ci:** drop removed python-version input from setup-uv and pin cache glob ([c1a9404](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/c1a94046459bfcdeb2e1ff537e25100be2d4e699))
* **router:** omit deprecated 'temperature' for Opus 4.x models ([558b24d](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/558b24dfcaa755f2d8a2f760448e644f225fd8a9))


### Features

* **api:** FastAPI endpoints with SSE per-run streaming ([36fde35](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/36fde3579aca6b0149118dcc76c0ce338ffa6602)), closes [#19](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/19)
* **api:** multi-rule runs + doc-text endpoint for evidence highlighting ([65e21a4](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/65e21a42b55538686494669cc61522bee333d12c)), closes [#6](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/6)
* **db:** postgres persistence + content-addressed findings cache ([90e6c43](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/90e6c4366df3e0c275b8dc82d9cee97111db3241)), closes [#11](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/11)
* **dsl:** add pydantic v2 rule schema with 5 ops ([fcaeea2](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/fcaeea23aa23c8eba98546f1f67d82495bc913b0)), closes [#6](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/6)
* **dsl:** compile rules into content-addressed atomic-check DAG ([ab3107f](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/ab3107f327872a80c32bcbe35eb7736c47fc7e4f)), closes [#12](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/12)
* **executor:** atomic check via router with page-stamped evidence ([cd82074](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/cd82074ef4c3f41d93f753dfcfbcb3161b1e8ca4)), closes [#15](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/15)
* **executor:** orchestrator fans out leaves and aggregates with degraded semantics ([3d21d0c](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/3d21d0c669d61fe95953e62244e449f55af658f7)), closes [#6](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/6) [#17](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/17) [#17](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/17)
* **frontend:** React run-view UI with swimlane DAG + live SSE flips ([fc0b154](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/fc0b154940263e5cb8fa559ba589c4763f48a46c))
* **ingest:** pypdf parser + tiktoken chunker with page-stamped DocChunks ([81e239e](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/81e239efd61dbc2f1af4822fdf41daf43960e314))
* **obs:** wire OpenTelemetry tracing with OTLP export and smoke check ([8270192](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/8270192eddadf7bd999466f889f1b32c82242524))
* **router:** add anthropic, openai, and mock provider adapters ([74f933c](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/74f933cc32852637b170397629d428216f35bd7a)), closes [#9](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/9)
* **router:** add retry, circuit breaker, and failover orchestrator ([7e200bb](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/7e200bbbbf3ebbebf9f670f40eb17dca29d4a49f))
* **rules+executor:** five FINRA-2210 rules + prompt tuning + hallucination guard ([feb94ec](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/feb94ec7fe77b879d1b12c7380a685062769b02d))

# [1.9.0](https://github.com/xbt-a4224j/compliance-workflow-demo/compare/v1.8.0...v1.9.0) (2026-04-19)


### Features

* **api:** FastAPI endpoints with SSE per-run streaming ([e11359a](https://github.com/xbt-a4224j/compliance-workflow-demo/commit/e11359af0fe0656942264e590d6ed01cd7edb07b)), closes [#19](https://github.com/xbt-a4224j/compliance-workflow-demo/issues/19)

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
