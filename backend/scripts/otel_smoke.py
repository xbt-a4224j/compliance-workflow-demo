"""Emit a parent+child span against the configured OTLP endpoint and flush."""

from __future__ import annotations

import time

from compliance_workflow_demo.obs.tracing import configure_tracing, force_flush


def main() -> None:
    tracer = configure_tracing(service_name="compliance-workflow-demo-smoke")
    with tracer.start_as_current_span("smoke.root") as root:
        root.set_attribute("smoke.kind", "otel-pipeline")
        with tracer.start_as_current_span("smoke.child") as child:
            child.set_attribute("smoke.step", "inner")
            time.sleep(0.01)
    force_flush()


if __name__ == "__main__":
    main()
