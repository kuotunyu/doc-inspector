"""Traditional-Chinese local Gradio interface for the inspection service."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from html import escape
import os
from pathlib import Path
import socket
from tempfile import gettempdir
from uuid import uuid4

import gradio as gr

from doc_inspector.config import load_settings
from doc_inspector.demo import generate_demo_artifacts
from doc_inspector.errors import DocInspectorError
from doc_inspector.rate_limit import HourlyRequestLimiter
from doc_inspector.exporters import (
    export_bundle_excel,
    export_bundle_json,
    extraction_table_rows,
)
from doc_inspector.schemas import InspectionBundle, RuleResult
from doc_inspector.service import inspect_document
from doc_inspector.types import ProviderName, SchemaName

CIVIC_CSS = """
:root {
  --ui-bg: oklch(96.8% 0.009 205);
  --ui-surface: oklch(99.2% 0.004 205);
  --ui-surface-soft: oklch(97.7% 0.009 205);
  --ui-surface-muted: oklch(94.6% 0.015 205);
  --ui-surface-accent: oklch(92.2% 0.034 205);
  --ui-ink: oklch(24% 0.036 205);
  --ui-muted: oklch(43% 0.026 205);
  --ui-border: oklch(86% 0.018 205);
  --ui-border-strong: oklch(73% 0.028 205);
  --ui-primary: oklch(49% 0.1 205);
  --ui-primary-hover: oklch(40% 0.085 205);
  --ui-primary-soft: oklch(94.5% 0.03 205);
  --ui-focus: oklch(58% 0.13 205);
  --ui-navy: oklch(24% 0.055 205);
  --ui-navy-soft: oklch(29% 0.05 205);
  --ui-danger-bg: oklch(96.5% 0.025 25);
  --ui-danger-border: oklch(57% 0.16 25);
  --ui-danger-ink: oklch(39% 0.13 25);
  --ui-warning-bg: oklch(97% 0.04 82);
  --ui-warning-border: oklch(64% 0.13 75);
  --ui-warning-ink: oklch(41% 0.085 75);
  --ui-success-bg: oklch(96% 0.025 150);
  --ui-success-border: oklch(53% 0.11 150);
  --ui-success-ink: oklch(37% 0.09 150);
  --space-xs: 8px;
  --space-sm: 10px;
  --space-md: 16px;
  --space-lg: 22px;
  --space-xl: 28px;
  --radius-sm: 8px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --shadow-soft: 0 6px 14px oklch(24% 0.036 205 / 0.1);
}

html,
body {
  background: var(--ui-bg) !important;
}

gradio-app {
  background: var(--ui-bg) !important;
}

.gradio-container {
  width: 100% !important;
  max-width: 1700px !important;
  margin: 0 auto !important;
  padding: 16px clamp(12px, 2.5vw, 40px) 40px !important;
  box-sizing: border-box !important;
  background: transparent !important;
  color: var(--ui-ink) !important;
  font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei UI",
    "Microsoft JhengHei", sans-serif !important;
  font-size: 21px !important;
  line-height: 1.55;
  --text-xs: 17px;
  --text-sm: 19px;
  --text-md: 20px;
  --text-lg: 22px;
  --text-xl: 27px;
  --text-xxl: 32px;
}

.gradio-container div.main.fillable.app {
  padding-right: clamp(4px, 1vw, 16px) !important;
  padding-left: clamp(4px, 1vw, 16px) !important;
  background: transparent !important;
}

.gradio-container .block.padded.hide-container > .html-container {
  padding: 0 !important;
}

.gradio-container p,
.gradio-container label,
.gradio-container input,
.gradio-container textarea,
.gradio-container button,
.gradio-container select,
.gradio-container table {
  font-size: 20px !important;
}

.masthead {
  display: grid;
  grid-template-columns: minmax(390px, 0.78fr) minmax(0, 1.22fr);
  gap: 0;
  align-items: stretch;
  overflow: hidden;
  margin: 0 0 12px;
  padding: 0;
  border: 1px solid oklch(79% 0.028 205);
  border-radius: var(--radius-lg);
  background: var(--ui-surface);
  box-shadow: 0 5px 12px oklch(24% 0.036 205 / 0.14);
}

.app-header {
  min-width: 0;
  padding: 22px 28px;
  margin: 0;
  background: var(--ui-navy);
  color: #ffffff;
}

.app-header h1 {
  margin: 0;
  color: #ffffff;
  font-size: 44px;
  font-weight: 780;
  line-height: 1.15;
  letter-spacing: -0.025em;
  text-wrap: balance;
}

.app-header p {
  max-width: 64ch;
  margin: 7px 0 0;
  color: oklch(90% 0.018 205);
  font-size: 20px !important;
  line-height: 1.5;
  text-wrap: pretty;
}

.result-legend {
  display: grid;
  grid-template-columns: 148px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  margin: 0;
  padding: 16px 18px;
  border: 0;
  border-radius: 0;
  background: var(--ui-surface-soft);
  box-shadow: none;
}

.legend-intro {
  min-width: 0;
}

.result-legend h2 {
  margin: 0;
  color: var(--ui-ink);
  font-size: 22px;
  font-weight: 800;
  line-height: 1.25;
}

.legend-intro p {
  margin: 3px 0 0;
  color: var(--ui-muted);
  font-size: 18px !important;
  line-height: 1.35;
}

.legend-items {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.legend-items li {
  display: flex;
  min-width: 0;
  min-height: 64px;
  gap: 9px;
  align-items: center;
  padding: 9px 11px;
  border: 1px solid;
  border-radius: var(--radius-sm);
  color: var(--ui-ink);
  font-size: 18px;
  line-height: 1.35;
}

.legend-red {
  border-color: oklch(86% 0.065 25) !important;
  background: var(--ui-danger-bg);
}

.legend-yellow {
  border-color: oklch(87% 0.075 82) !important;
  background: var(--ui-warning-bg);
}

.legend-green {
  border-color: oklch(84% 0.055 150) !important;
  background: var(--ui-success-bg);
}

.legend-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.legend-items strong {
  color: var(--ui-ink);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.2;
}

.legend-action {
  margin-top: 2px;
  color: var(--ui-muted);
  font-size: 18px;
  line-height: 1.3;
}

.legend-dot {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  border-radius: 50%;
  box-shadow: 0 0 0 3px oklch(99% 0 0 / 0.72);
}

.legend-dot-red {
  background: oklch(68% 0.18 25);
}

.legend-dot-yellow {
  background: oklch(78% 0.15 78);
}

.legend-dot-green {
  background: oklch(67% 0.13 150);
}

.workbench {
  gap: 0 !important;
  align-items: stretch !important;
  overflow: hidden;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--ui-surface);
  box-shadow: var(--shadow-soft);
}

.workflow-section {
  gap: 8px !important;
  min-width: 0 !important;
  padding: 16px 28px !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.workflow-section + .workflow-section {
  border-top: 1px solid var(--ui-border) !important;
}

.action-section {
  background: var(--ui-surface-soft) !important;
}

.task-heading {
  display: flex;
  gap: 13px;
  align-items: flex-start;
  margin: 0;
}

.task-heading-copy {
  min-width: 0;
}

.task-heading h2,
.task-heading h3 {
  margin: 0;
  color: var(--ui-ink);
  line-height: 1.25;
  text-wrap: balance;
}

.task-heading h2 {
  font-size: 28px;
  font-weight: 780;
  letter-spacing: -0.02em;
}

.task-heading h3 {
  font-size: 26px;
  font-weight: 740;
}

.task-heading p {
  max-width: 70ch;
  margin: 3px 0 0;
  color: var(--ui-muted);
  font-size: 20px !important;
  line-height: 1.45;
}

.task-step {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--ui-primary);
  color: #ffffff;
  font-size: 20px;
  font-weight: 800;
  line-height: 1;
}

.upload-control {
  flex: 0 0 auto !important;
  height: 132px !important;
  min-height: 132px !important;
  border: 2px dashed #a8bbc0 !important;
  border-radius: var(--radius-md) !important;
  background: #f8fafb !important;
  box-shadow: none !important;
  transition:
    border-color 160ms ease-out,
    background-color 160ms ease-out;
}

.upload-control > button {
  height: 100% !important;
}

.upload-control > button > .wrap {
  height: auto !important;
  min-height: 0 !important;
  padding: 4px 0 6px !important;
  font-size: 20px !important;
  line-height: 1.3 !important;
}

.upload-control > button > .wrap .icon-wrap {
  margin-bottom: 2px !important;
}

.upload-control > button > .wrap .or {
  font-size: 18px !important;
  line-height: 1.2 !important;
}

.upload-control:hover {
  border-color: var(--ui-primary) !important;
  background: var(--ui-primary-soft) !important;
}

.upload-control,
.field-control,
.consent-control,
.download-control {
  font-size: 20px !important;
}

.field-control label,
.upload-control label,
.download-control label {
  color: var(--ui-ink) !important;
  font-size: 20px !important;
  font-weight: 700 !important;
}

#schema-selector [data-testid="block-info"],
#provider-selector [data-testid="block-info"] {
  color: var(--ui-muted) !important;
  font-size: 18px !important;
  font-weight: 650 !important;
  line-height: 1.45 !important;
}

.field-control input,
.field-control [role="combobox"],
.field-control button {
  min-height: 56px !important;
  font-size: 20px !important;
}

.field-control,
#demo-selector {
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  overflow: visible !important;
}

.field-control > .container > .wrap,
#demo-selector > .container > .wrap {
  border: 1px solid var(--ui-border-strong) !important;
  border-radius: var(--radius-md) !important;
  background: var(--ui-surface) !important;
  box-shadow: none !important;
  transition: border-color 150ms ease-out, box-shadow 150ms ease-out;
}

.field-control:hover > .container > .wrap,
#demo-selector:hover > .container > .wrap {
  border-color: var(--ui-primary) !important;
  box-shadow: 0 0 0 3px rgba(13, 102, 115, 0.09) !important;
}

.upload-guidance {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  color: var(--ui-muted);
  font-size: 18px;
}

.upload-guidance span {
  position: static;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--ui-surface-muted);
}

.upload-guidance span::before {
  content: none;
}

.source-brief {
  display: grid;
  grid-template-columns: 164px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  padding: 9px 12px;
  border: 1px solid oklch(88% 0.03 205);
  border-radius: var(--radius-sm);
  background: var(--ui-primary-soft);
  color: var(--ui-muted);
}

.source-brief h3 {
  margin: 0;
  color: var(--ui-primary-hover);
  font-size: 21px;
  font-weight: 760;
  line-height: 1.45;
}

.source-brief p {
  margin: 0;
  font-size: 19px !important;
  line-height: 1.45;
}

.source-brief strong {
  color: var(--ui-ink);
}

.demo-heading {
  display: block;
  margin: 0;
}

.demo-heading h3 {
  margin: 0;
  color: var(--ui-ink);
  font-size: 22px;
  font-weight: 760;
  line-height: 1.4;
}

.demo-heading p {
  margin: 1px 0 0;
  color: var(--ui-muted);
  font-size: 18px !important;
  line-height: 1.45;
}

.demo-controls {
  gap: var(--space-sm) !important;
  align-items: center !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.demo-controls > .form {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.demo-heading-block {
  min-width: 220px !important;
  flex: 0 0 220px !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.demo-heading-block .prose {
  display: flex;
  height: 100%;
  flex-direction: column;
  justify-content: center;
}

#demo-selector label span {
  color: var(--ui-muted) !important;
  font-size: 19px !important;
}

#demo-selector input,
#demo-selector [role="combobox"],
#demo-selector button {
  min-height: 56px !important;
  font-size: 20px !important;
}

#demo-selector {
  min-height: 56px !important;
}

.demo-btn {
  min-height: 56px !important;
  border: 1px solid var(--ui-primary) !important;
  border-radius: var(--radius-md) !important;
  background: var(--ui-surface) !important;
  color: var(--ui-primary) !important;
  font-size: 20px !important;
  font-weight: 740 !important;
}

.demo-btn:hover {
  background: var(--ui-primary-soft) !important;
  box-shadow: none !important;
}

.demo-status {
  min-height: 0 !important;
}

.block.demo-status:has(.prose:empty) {
  display: none !important;
}

.demo-status p {
  margin: 0;
  color: var(--ui-muted);
  font-size: 18px !important;
  line-height: 1.45;
}

.demo-status strong {
  color: var(--ui-primary);
}

.control-grid {
  gap: 14px !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.control-grid > .form {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.notice-grid {
  flex-direction: row !important;
  gap: 22px !important;
  align-items: center !important;
  overflow: visible;
  padding: 12px 15px !important;
  border: 1px solid oklch(86% 0.03 205) !important;
  border-radius: var(--radius-md) !important;
  background: var(--ui-primary-soft) !important;
  box-shadow: none !important;
}

.notice-grid > .form {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  overflow: visible !important;
}

.privacy-block {
  flex: 6 1 0% !important;
  min-width: min(300px, 100%) !important;
}

.privacy-note {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ui-muted);
}

.privacy-note strong {
  display: block;
  margin-bottom: 4px;
  color: var(--ui-ink);
  font-size: 21px;
}

.privacy-note p {
  margin: 0;
  color: var(--ui-muted);
  font-size: 19px !important;
  line-height: 1.45;
}

#cloud-consent {
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  overflow: visible !important;
}

#cloud-consent .wrap {
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  overflow: visible !important;
}

#cloud-consent > div,
#cloud-consent .form,
#cloud-consent .container,
#cloud-consent label {
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

#cloud-consent label {
  display: flex !important;
  min-height: 44px !important;
  padding: 0 !important;
  align-items: center !important;
  color: var(--ui-ink) !important;
  font-weight: 720 !important;
  cursor: pointer !important;
}

#cloud-consent input[type="checkbox"] {
  width: 22px !important;
  height: 22px !important;
  accent-color: var(--ui-primary);
}

#cloud-consent span.label-text {
  color: var(--ui-ink) !important;
  font-size: 20px !important;
  line-height: 1.4 !important;
}

#cloud-consent .info,
#cloud-consent div.info-text {
  color: var(--ui-muted) !important;
  font-size: 18px !important;
  line-height: 1.45 !important;
}

.primary-btn {
  min-height: 56px !important;
  border: 0 !important;
  border-radius: var(--radius-md) !important;
  background: var(--ui-primary) !important;
  color: #ffffff !important;
  font-size: 20px !important;
  font-weight: 780 !important;
  letter-spacing: 0.02em;
  box-shadow: none !important;
  transition:
    background-color 160ms ease-out,
    transform 160ms ease-out;
}

.primary-btn:hover {
  background: var(--ui-primary-hover) !important;
  transform: translateY(-1px);
}

.primary-btn:active {
  transform: translateY(0);
}

.primary-btn:disabled {
  background: #557888 !important;
  cursor: progress !important;
  opacity: 1 !important;
  box-shadow: none !important;
  transform: none;
}

.action-grid {
  gap: 12px !important;
  align-items: center !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.status-output {
  flex: 7 1 0% !important;
  min-width: min(300px, 100%) !important;
  align-self: stretch !important;
  min-height: 0 !important;
  margin-top: 0 !important;
}

.status-card {
  min-height: 0;
  height: 100%;
  box-sizing: border-box;
  padding: 11px 13px;
  border: 1px solid var(--ui-border);
  border-radius: var(--radius-md);
  background: var(--ui-surface);
  color: var(--ui-ink);
  font-size: 19px;
}

.status-card strong {
  display: block;
  margin-bottom: 2px;
  font-size: 21px;
}

.status-card p {
  margin: 0;
}

.status-card .status-next {
  margin-top: 5px;
  font-weight: 690;
}

.status-card.status-red {
  border-color: var(--ui-danger-border);
  background: var(--ui-danger-bg);
  color: var(--ui-danger-ink);
}

.status-card.status-yellow {
  border-color: var(--ui-warning-border);
  background: var(--ui-warning-bg);
  color: var(--ui-warning-ink);
}

.status-card.status-green {
  border-color: var(--ui-success-border);
  background: var(--ui-success-bg);
  color: var(--ui-success-ink);
}

.status-card.status-processing {
  border-color: #77a4b8;
  background: #edf5f7;
}

.status-meta {
  display: block;
  margin-top: var(--space-xs);
  color: var(--ui-muted);
  font-size: 18px;
}

.status-red .status-meta {
  color: var(--ui-danger-ink);
}

.status-yellow .status-meta {
  color: var(--ui-warning-ink);
}

.status-green .status-meta {
  color: var(--ui-success-ink);
}

.result-link {
  display: inline-block;
  margin-top: 6px;
  color: var(--ui-primary);
  font-size: 18px;
  font-weight: 740;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.results-heading {
  margin-top: 22px;
  margin-bottom: 10px;
  padding: 0 4px;
}

.action-plan {
  overflow: hidden;
  margin-bottom: 12px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--ui-surface);
  box-shadow: 0 2px 8px rgba(17, 41, 50, 0.06);
}

.action-plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 18px;
  background: var(--ui-surface-muted);
}

.action-plan-header h3 {
  margin: 0;
  color: var(--ui-ink);
  font-size: 24px;
  font-weight: 760;
  line-height: 1.35;
}

.action-plan-header p {
  margin: 3px 0 0;
  color: var(--ui-muted);
  font-size: 19px !important;
  line-height: 1.45;
}

.action-plan-clear .action-plan-header {
  background: var(--ui-success-bg);
}

.action-plan-empty .action-plan-header {
  background: #f7f9f8;
}

.issue-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.issue-item {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 18px;
  padding: 15px 18px;
  border-top: 1px solid var(--ui-border);
}

.issue-level {
  align-self: start;
  padding: 5px 8px;
  border-radius: 7px;
  font-size: 18px;
  font-weight: 750;
  line-height: 1.35;
  text-align: center;
}

.issue-red .issue-level {
  background: var(--ui-danger-bg);
  color: #9b2c1f;
}

.issue-yellow .issue-level {
  background: var(--ui-warning-bg);
  color: #735600;
}

.issue-content strong {
  display: block;
  color: var(--ui-ink);
  font-size: 21px;
  line-height: 1.4;
}

.issue-content p {
  margin: 3px 0 0;
  color: var(--ui-muted);
  font-size: 19px !important;
  line-height: 1.5;
}

.issue-content .issue-values {
  color: #40565f;
  font-size: 18px !important;
}

.issue-content .issue-action {
  color: var(--ui-ink);
}

.action-plan-next {
  margin: 0;
  padding: 13px 18px;
  border-top: 1px solid var(--ui-border);
  background: #f7f9f8;
  color: var(--ui-ink);
  font-size: 19px !important;
  line-height: 1.45;
}

.result-tabs {
  overflow: hidden;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--ui-surface);
  box-shadow: 0 2px 8px rgba(17, 41, 50, 0.06);
}

.result-tabs .tab-wrapper {
  gap: 4px !important;
  padding: 5px 7px !important;
  border-bottom: 1px solid var(--ui-border) !important;
  background: var(--ui-surface-muted) !important;
}

.result-tabs .tab-container.visually-hidden {
  display: none !important;
}

.result-tabs .tab-container[role="tablist"] {
  display: flex;
  min-width: 0;
  overflow-x: auto;
}

.result-tabs button[role="tab"] {
  min-height: 46px;
  padding-inline: 16px !important;
  border-radius: var(--radius-sm) !important;
  color: var(--ui-muted) !important;
  background: transparent !important;
  font-size: 19px !important;
  font-weight: 700 !important;
}

.result-tabs button[role="tab"][aria-selected="true"] {
  color: var(--ui-primary) !important;
  background: var(--ui-surface) !important;
  box-shadow: none !important;
}

.result-table-scroll {
  max-height: 520px;
  overflow: auto;
  background: var(--ui-surface);
  scrollbar-gutter: stable;
}

.result-table {
  width: 100%;
  border-spacing: 0;
  border-collapse: separate;
  color: var(--ui-ink);
  font-size: 19px !important;
  text-align: left;
}

.result-table caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.extraction-result-table {
  min-width: 950px;
}

.checks-result-table {
  min-width: 1180px;
}

.result-table th {
  position: sticky;
  z-index: 1;
  top: 0;
  min-height: 44px;
  border: 0 !important;
  border-bottom: 1px solid var(--ui-border) !important;
  background: var(--ui-surface-muted);
  color: var(--ui-ink);
  font-weight: 740;
}

.result-table td {
  border: 0 !important;
  border-bottom: 1px solid #e2e9ea !important;
  background: var(--ui-surface);
  color: var(--ui-ink);
  vertical-align: top;
}

.result-table th,
.result-table td {
  padding: 12px 14px !important;
  font-size: 19px !important;
  line-height: 1.5 !important;
  overflow-wrap: anywhere;
}

.result-table th:not(:last-child),
.result-table td:not(:last-child) {
  border-right: 1px solid #e2e9ea !important;
}

.result-table tbody tr:last-child td {
  border-bottom: 0 !important;
}

.result-table .result-empty {
  min-height: 62px;
  padding: 18px !important;
  background: var(--ui-surface-soft);
  color: var(--ui-muted);
  font-size: 18px;
}

.downloads-heading {
  display: block;
  margin-top: 18px;
  padding: 0 4px;
}

.downloads-heading h3 {
  margin: 0;
  color: var(--ui-ink);
  font-size: 25px;
  font-weight: 760;
  line-height: 1.35;
}

.downloads-heading p {
  margin: 3px 0 0;
  color: var(--ui-muted);
  font-size: 19px !important;
  line-height: 1.45;
}

.download-row {
  gap: 14px !important;
}

.download-control {
  min-height: 54px !important;
  border: 1px solid var(--ui-primary) !important;
  border-radius: var(--radius-md) !important;
  background: var(--ui-surface) !important;
  color: var(--ui-primary) !important;
  font-size: 20px !important;
  font-weight: 740 !important;
  box-shadow: none !important;
  transition:
    border-color 150ms ease-out,
    background-color 150ms ease-out,
    transform 150ms ease-out;
}

.download-control:hover {
  border-color: var(--ui-primary-hover) !important;
  background: var(--ui-primary-soft) !important;
  transform: translateY(-1px);
}

.gradio-container button:focus-visible,
.gradio-container input:focus-visible,
.gradio-container textarea:focus-visible,
.gradio-container a:focus-visible,
.gradio-container [role="combobox"]:focus-visible,
.gradio-container [role="tab"]:focus-visible,
.gradio-container [role="region"]:focus-visible {
  outline: 3px solid var(--ui-focus) !important;
  outline-offset: 2px !important;
}

footer {
  display: none !important;
}

@media (max-width: 1180px) and (min-width: 821px) {
  .masthead {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .result-legend {
    grid-template-columns: 170px minmax(0, 1fr);
  }
}

@media (max-width: 820px) {
  .gradio-container.gradio-container-6-20-0.fill_width {
    width: 100vw !important;
    max-width: 100vw !important;
    padding: 10px 8px 28px !important;
    box-sizing: border-box !important;
    font-size: 19px !important;
  }

  .gradio-container div.main.fillable.app.fill_width {
    padding-right: 0 !important;
    padding-left: 0 !important;
  }

  .masthead {
    grid-template-columns: 1fr;
    gap: 0;
    margin-bottom: 10px;
    padding: 0;
  }

  .app-header {
    padding: 18px 17px;
  }

  .app-header h1 {
    font-size: 36px;
  }

  .app-header p {
    font-size: 19px !important;
    line-height: 1.45;
  }

  .result-legend {
    display: block;
    padding: 12px;
  }

  .result-legend h2 {
    font-size: 21px;
  }

  .legend-intro {
    display: flex;
    gap: 9px;
    align-items: baseline;
    margin-bottom: 8px;
  }

  .legend-intro p {
    margin: 0;
    font-size: 18px !important;
  }

  .legend-items {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }

  .legend-items li {
    min-height: 94px;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
    padding: 8px;
    font-size: 18px !important;
  }

  .legend-items strong {
    font-size: 20px;
  }

  .legend-copy {
    flex-direction: column;
    gap: 2px;
    align-items: flex-start;
  }

  .legend-action {
    margin-top: 0;
    font-size: 18px;
    line-height: 1.25;
  }

  .upload-control {
    height: 132px !important;
    min-height: 132px !important;
  }

  .demo-heading-block {
    min-width: 0 !important;
    flex: 0 0 auto !important;
  }

  .workbench {
    overflow: visible;
  }

  .demo-heading {
    display: block;
  }

  .source-brief {
    grid-template-columns: 1fr;
    gap: 3px;
    padding: 9px 12px;
  }

  .workflow-section {
    width: 100% !important;
    flex: 1 1 auto !important;
    padding: 14px 16px !important;
  }

  .task-heading {
    gap: 10px;
  }

  .task-heading h2 {
    font-size: 26px;
  }

  .task-heading p {
    font-size: 19px !important;
  }

  .control-grid {
    flex-direction: column !important;
  }

  .demo-controls {
    flex-direction: column !important;
    align-items: stretch !important;
  }

  .demo-controls > div,
  .demo-btn {
    width: 100% !important;
  }

  .notice-grid,
  .action-grid {
    flex-direction: column !important;
  }

  .notice-grid {
    gap: 12px !important;
    align-items: stretch !important;
    padding: 13px !important;
  }

  .privacy-block,
  .status-output {
    flex: 0 0 auto !important;
    min-width: 100% !important;
  }

  .privacy-note p,
  #cloud-consent span.label-text {
    font-size: 19px !important;
  }

  .action-grid > div,
  .action-grid > button {
    width: 100% !important;
  }

  .primary-btn {
    min-height: 54px !important;
    font-size: 20px !important;
  }

  .results-heading {
    margin-top: 22px;
  }

  .action-plan-header {
    padding: 13px 14px;
  }

  .action-plan-header h3 {
    font-size: 21px;
  }

  .issue-item {
    grid-template-columns: 1fr;
    gap: 8px;
    padding: 14px;
  }

  .issue-level {
    justify-self: start;
  }

  .action-plan-next {
    padding: 12px 14px;
  }

  .result-table-scroll {
    overflow-x: auto !important;
  }

  #extraction-table table {
    width: 950px !important;
    min-width: 950px !important;
  }

  #checks-table table {
    width: 1180px !important;
    min-width: 1180px !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  .primary-btn,
  .upload-control,
  .download-control,
  .field-control,
  #demo-selector {
    transition: none;
  }
}
"""

_FIELD_LABELS = {
    "program_name": "補助方案",
    "application_date": "申請日期",
    "applicants": "申請人",
    "beneficiaries": "受益人",
    "role": "身分角色",
    "name": "姓名",
    "id_type": "證件類型",
    "id_number": "證件號碼",
    "birth_date": "出生日期",
    "contact_phone": "聯絡電話",
    "contact_email": "電子郵件",
    "address": "地址",
    "bank_account_display_name": "撥款帳戶名稱",
    "requested_amount": "申請金額",
    "line_items": "明細",
    "description": "項目說明",
    "amount": "金額",
    "declared_total": "申報總額",
    "merchant_name": "店家名稱",
    "receipt_number": "收據／發票號碼",
    "receipt_date": "收據／發票日期",
    "currency": "幣別",
    "quantity": "數量",
    "unit_price": "單價",
    "line_total": "品項金額",
    "subtotal": "小計",
    "tax": "稅額",
    "discount": "折扣",
    "fees": "其他費用",
    "total": "總額",
    "additional_fields": "其他欄位",
    "located_value": "內容",
}

_COLLECTION_LABELS = {
    "applicants": "申請人",
    "beneficiaries": "受益人",
    "line_items": "明細",
    "additional_fields": "其他欄位",
}

_ID_TYPE_LABELS = {
    "citizen_id": "台灣身分證",
    "resident_id": "居留證",
    "passport": "護照",
    "other": "其他證件",
    "unknown": "未判定",
}

_RULE_LABELS = {
    "required.value": "必填欄位",
    "required.list": "必要資料",
    "date.parse": "日期格式",
    "date.birth_before_application": "日期先後",
    "identity.document": "證件號碼",
    "identity.citizen_id": "身分證字號",
    "identity.manual_review": "證件人工確認",
    "amount.parse": "金額格式",
    "amount.subsidy_line_total": "補助明細加總",
    "amount.requested_vs_declared": "申請金額一致",
    "amount.receipt_line": "品項金額",
    "amount.receipt_subtotal": "收據小計",
    "amount.receipt_total": "收據總額",
}

_CHECK_LEVEL_LABELS = {
    "red": "🔴 請修改",
    "yellow": "🟡 請確認",
    "green": "🟢 未發現問題",
}
_EXTRACTION_HEADERS = ("欄位", "辨識內容", "頁碼", "文件原文")
_CHECK_HEADERS = (
    "檢核項目",
    "結果",
    "說明",
    "相關欄位",
    "目前值",
    "應符合",
)

_DEMO_OPTIONS: dict[str, tuple[str, SchemaName]] = {
    "subsidy_green": ("補助｜綠燈範例", "subsidy_application"),
    "subsidy_yellow": ("補助｜黃燈範例", "subsidy_application"),
    "subsidy_red": ("補助｜紅燈範例", "subsidy_application"),
    "receipt_green": ("收據｜綠燈範例", "receipt"),
}

Inspector = Callable[[Path, SchemaName, ProviderName], InspectionBundle]
RequestGuard = Callable[[], None]


def gradio_temp_root() -> Path:
    """Return the absolute cache root shared by Gradio and generated downloads."""

    configured = os.environ.get("GRADIO_TEMP_DIR")
    candidate = (
        Path(configured)
        if configured
        else Path(gettempdir()) / "doc-inspector-gradio"
    )
    if configured and not candidate.is_absolute():
        raise RuntimeError("GRADIO_TEMP_DIR 必須是絕對路徑。")
    return candidate.resolve()


def prepare_gradio_temp_root() -> Path:
    """Create and publish the managed cache root before components are built."""

    root = gradio_temp_root()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["GRADIO_TEMP_DIR"] = str(root)
    return root


def _humanize_field_path(path: str) -> str:
    """Translate a machine field path into a short Traditional-Chinese label."""

    parts = path.split(".")
    labels: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if (
            part in _COLLECTION_LABELS
            and index + 1 < len(parts)
            and parts[index + 1].isdigit()
        ):
            labels.append(f"{_COLLECTION_LABELS[part]} {int(parts[index + 1]) + 1}")
            index += 2
            continue
        if part.isdigit():
            labels.append(f"第 {int(part) + 1} 筆")
        else:
            labels.append(_FIELD_LABELS.get(part, part))
        index += 1
    return "／".join(labels)


def _humanize_check_message(check: RuleResult) -> str:
    if check.rule_id == "required.value":
        return "必要欄位已提供。" if check.level == "green" else "必要欄位沒有內容。"
    if check.rule_id == "date.parse":
        if check.level == "green":
            return "日期格式有效。"
        if check.level == "yellow":
            return "缺少日期，無法檢查。"
        return "日期格式或日期內容無效。"
    if check.rule_id == "amount.parse":
        if check.level == "green":
            return "金額格式可讀。"
        if check.level == "yellow":
            return "缺少金額，無法計算。"
        return "金額格式無效。"
    message = check.message
    for path in sorted(check.field_paths, key=len, reverse=True):
        message = message.replace(path, _humanize_field_path(path))
    for raw_value, label in _ID_TYPE_LABELS.items():
        message = message.replace(f"證件種類 {raw_value}", f"證件種類「{label}」")
    return message


def _check_fields(check: RuleResult) -> str:
    labels = list(dict.fromkeys(_humanize_field_path(path) for path in check.field_paths))
    return "、".join(labels) or "整份文件"


def _check_action(check: RuleResult) -> str:
    field = _humanize_field_path(check.field_paths[0]) if check.field_paths else "這個欄位"
    if check.rule_id == "required.value":
        return f"回原文件補上「{field}」。"
    if check.rule_id == "required.list":
        if "line_items" in check.field_paths:
            return "回原文件至少補上一筆明細。"
        return "回原文件至少補上一位申請人。"
    if check.rule_id == "date.parse":
        if check.level == "yellow":
            return f"回原文件補上「{field}」。"
        return "改成有效日期，例如 2026-07-23、2026/07/23 或清楚的民國日期。"
    if check.rule_id == "date.birth_before_application":
        return "對照原文件確認出生日期與申請日期；出生日期不可晚於申請日期。"
    if check.rule_id == "identity.document":
        return "回原文件補上證件號碼，再重新預檢。"
    if check.rule_id == "identity.citizen_id":
        return "逐字核對身分證字號，修正字數、英文字母或檢查碼。"
    if check.rule_id == "identity.manual_review":
        return "對照原始證件確認種類與號碼；此項需由人工判斷。"
    if check.rule_id == "amount.parse":
        return "把金額改成清楚的數字，例如 1,200 或 1200。"
    if check.rule_id == "amount.subsidy_line_total":
        return "重新加總每筆補助明細，讓合計等於申報總額。"
    if check.rule_id == "amount.requested_vs_declared":
        return "確認申請金額與申報總額應相同，修正其中一處。"
    if check.rule_id == "amount.receipt_line":
        return "核對數量 × 單價是否等於品項金額。"
    if check.rule_id == "amount.receipt_subtotal":
        return "重新加總各品項，讓合計等於小計。"
    if check.rule_id == "amount.receipt_total":
        return "核對小計、稅額、折扣及其他費用，讓計算結果等於總額。"
    return "對照原文件確認這項內容，必要時修正後再預檢。"


def _check_detail_text(check: RuleResult) -> str:
    comparison_labels = {
        "amount.subsidy_line_total": ("明細加總", "申報總額"),
        "amount.requested_vs_declared": ("申請金額", "申報總額"),
        "amount.receipt_line": ("數量 × 單價", "品項金額"),
        "amount.receipt_subtotal": ("品項加總", "小計"),
        "amount.receipt_total": ("計算結果", "總額"),
    }
    if (
        check.rule_id in comparison_labels
        and check.observed is not None
        and check.expected is not None
    ):
        observed_label, expected_label = comparison_labels[check.rule_id]
        return (
            f"{observed_label}：{check.observed}；"
            f"{expected_label}：{check.expected}"
        )
    details = []
    if check.observed:
        details.append(f"目前辨識：{check.observed}")
    if check.expected:
        details.append(f"應符合：{check.expected}")
    return "；".join(details)


def _display_extraction_rows(bundle: InspectionBundle) -> list[tuple]:
    rows = []
    for path, value, page_number, evidence in extraction_table_rows(bundle):
        display_value = _ID_TYPE_LABELS.get(value, value) if path.endswith("id_type") else value
        rows.append(
            (
                _humanize_field_path(path),
                display_value if display_value not in (None, "") else "未辨識到",
                page_number if page_number is not None else "—",
                evidence if evidence not in (None, "") else "—",
            )
        )
    return rows


def _display_check_rows(bundle: InspectionBundle) -> list[tuple]:
    return [
        (
            _RULE_LABELS.get(check.rule_id, check.rule_id),
            _CHECK_LEVEL_LABELS[check.level],
            _humanize_check_message(check),
            _check_fields(check),
            check.observed or "—",
            check.expected or "—",
        )
        for check in bundle.review_report.checks
    ]


def _result_table_html(
    *,
    caption: str,
    headers: tuple[str, ...],
    rows: list[tuple],
    table_class: str,
) -> str:
    """Render a read-only semantic table without editable Dataframe controls."""

    header_html = "".join(
        f'<th scope="col">{escape(header)}</th>' for header in headers
    )
    if rows:
        body_html = "".join(
            "<tr>"
            + "".join(f"<td>{escape(str(value))}</td>" for value in row)
            + "</tr>"
            for row in rows
        )
    else:
        body_html = (
            f'<tr><td class="result-empty" colspan="{len(headers)}">'
            "尚未執行預檢；完成後，資料會顯示在這裡。</td></tr>"
        )
    return (
        f'<div class="result-table-scroll" role="region" '
        f'aria-label="{escape(caption)}" tabindex="0">'
        f'<table class="result-table {escape(table_class)}">'
        f'<caption>{escape(caption)}</caption>'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )


def _action_plan_html(bundle: InspectionBundle) -> str:
    issues = [
        check
        for check in bundle.review_report.checks
        if check.level in {"red", "yellow"}
    ]
    issues.sort(key=lambda check: 0 if check.level == "red" else 1)
    red_count = sum(check.level == "red" for check in issues)
    yellow_count = sum(check.level == "yellow" for check in issues)
    if not issues:
        return (
            '<section class="action-plan action-plan-clear" aria-labelledby="action-plan-title">'
            '<div class="action-plan-header">'
            '<div><h3 id="action-plan-title">目前沒有需要修改的項目</h3>'
            "<p>系統規則未發現問題；送件前仍請人工確認內容與附件。</p></div>"
            "</div></section>"
        )

    summary_parts = []
    if red_count:
        summary_parts.append(f"{red_count} 項需要修改")
    if yellow_count:
        summary_parts.append(f"{yellow_count} 項需要人工確認")
    items = []
    for number, check in enumerate(issues, start=1):
        details = _check_detail_text(check)
        detail_html = (
            f'<p class="issue-values">{escape(details)}</p>'
            if details
            else ""
        )
        items.append(
            f'<li class="issue-item issue-{check.level}">'
            f'<span class="issue-level">{escape(_CHECK_LEVEL_LABELS[check.level])}</span>'
            '<div class="issue-content">'
            f"<strong>{number}. {escape(_check_fields(check))}</strong>"
            f"<p>{escape(_humanize_check_message(check))}</p>"
            f"{detail_html}"
            f'<p class="issue-action"><b>怎麼處理：</b>{escape(_check_action(check))}</p>'
            "</div></li>"
        )
    return (
        '<section class="action-plan" aria-labelledby="action-plan-title">'
        '<div class="action-plan-header">'
        '<div><h3 id="action-plan-title">先照這份清單處理</h3>'
        f"<p>{escape('；'.join(summary_parts))}。紅燈先修改，黃燈請對照原文件確認。</p></div>"
        "</div>"
        f'<ol class="issue-list">{"".join(items)}</ol>'
        '<p class="action-plan-next"><strong>改完後：</strong>'
        '回到上方換上修正後的文件，再按「再次預檢」。</p>'
        "</section>"
    )


def _status_html(bundle: InspectionBundle) -> str:
    checks = bundle.review_report.checks
    counts = {
        level: sum(check.level == level for check in checks)
        for level in ("red", "yellow", "green")
    }
    level = bundle.review_report.overall_level
    if level == "red":
        title = f"🔴 先修正 {counts['red']} 項"
        summary = (
            f"另有 {counts['yellow']} 項需要人工確認；"
            f"{counts['green']} 項目前沒有發現問題。"
        )
        next_step = "下一步：查看修正建議，修改原文件後再重新預檢。"
        link_label = "查看修正建議 ↓"
    elif level == "yellow":
        title = f"🟡 請確認 {counts['yellow']} 項"
        summary = f"沒有紅燈；{counts['green']} 項目前沒有發現問題。"
        next_step = "下一步：對照原文件人工確認，再決定是否修改。"
        link_label = "查看確認事項 ↓"
    else:
        title = "🟢 目前沒有發現問題"
        summary = f"共 {counts['green']} 項檢核目前沒有發現問題。"
        next_step = "下一步：送件前仍請人工確認內容與附件。"
        link_label = "查看檢核內容 ↓"
    return (
        f'<div class="status-card status-{level}" role="status" aria-live="polite">'
        f"<strong>{title}</strong>"
        f"<p>{summary}</p>"
        f'<p class="status-next">{next_step}</p>'
        f'<span class="status-meta">已檢查：{escape(bundle.source_file_name)}'
        f"（{bundle.page_count} 頁）</span>"
        f'<a class="result-link" href="#action-plan">{link_label}</a></div>'
    )


def ensure_local_port_available(port: int, server_name: str = "127.0.0.1") -> None:
    """Fail without stopping an unrelated process when the configured port is occupied."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((server_name, port))
        except OSError as exc:
            raise RuntimeError(
                f"{server_name}:{port} 已被其他程序使用；未終止該程序。"
            ) from exc


def run_inspection_callback(
    file_path: str | None,
    schema: SchemaName,
    provider: ProviderName,
    consent: bool,
    *,
    inspector: Inspector = inspect_document,
    export_root: Path | None = None,
    request_guard: RequestGuard | None = None,
) -> tuple[str, str, str, str, dict, str, str]:
    """Service-layer callback kept independently testable without starting Gradio."""

    if not consent:
        raise ValueError("請先勾選雲端傳送告知，確認你了解文件會送至選定供應商。")
    if not file_path:
        raise ValueError("請先選擇圖片或 PDF。")
    if request_guard is not None:
        request_guard()
    bundle = inspector(Path(file_path), schema, provider)
    root = export_root or gradio_temp_root()
    run_dir = root / uuid4().hex
    json_path = export_bundle_json(bundle, run_dir / "inspection.json")
    excel_path = export_bundle_excel(bundle, run_dir / "inspection.xlsx")
    return (
        _status_html(bundle),
        _action_plan_html(bundle),
        _result_table_html(
            caption="辨識內容",
            headers=_EXTRACTION_HEADERS,
            rows=_display_extraction_rows(bundle),
            table_class="extraction-result-table",
        ),
        _result_table_html(
            caption="全部檢核",
            headers=_CHECK_HEADERS,
            rows=_display_check_rows(bundle),
            table_class="checks-result-table",
        ),
        bundle.model_dump(mode="json"),
        str(json_path),
        str(excel_path),
    )


def inspection_update_stream(
    file_path: str | None,
    schema: SchemaName,
    provider: ProviderName,
    consent: bool,
    *,
    inspector: Inspector = inspect_document,
    export_root: Path | None = None,
    request_guard: RequestGuard | None = None,
) -> Iterator[tuple[object, ...]]:
    """Yield immediate, persistent UI feedback around one inspection request."""

    yield (
        '<div class="status-card status-processing" role="status" aria-live="polite">'
        "<strong>正在預檢，請稍候…</strong>"
        "<p>正在抽取欄位並執行規則檢核；完成前不需要重複點擊。</p></div>",
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.update(value="預檢進行中…", interactive=False),
    )

    try:
        result = run_inspection_callback(
            file_path,
            schema,
            provider,
            consent,
            inspector=inspector,
            export_root=export_root,
            request_guard=request_guard,
        )
    except (DocInspectorError, ValueError) as exc:
        yield (
            '<div class="status-card status-red" role="alert">'
            "<strong>無法開始預檢</strong>"
            f"<p>{escape(str(exc))}</p></div>",
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.update(value="開始預檢", interactive=True),
        )
        return

    yield (
        *result,
        gr.update(value="再次預檢", interactive=True),
    )


def load_demo_document_callback(
    demo_name: str | None,
    *,
    demo_root: Path | None = None,
) -> tuple[str, SchemaName, str]:
    """Generate and select a visibly synthetic document without calling an API."""

    if not demo_name or demo_name not in _DEMO_OPTIONS:
        raise ValueError("請先選擇一份合成範例。")

    root = demo_root or gradio_temp_root() / "demo"
    image_path = root / f"{demo_name}.png"
    if not image_path.is_file():
        artifacts = {
            artifact.name: artifact
            for artifact in generate_demo_artifacts(root)
        }
        image_path = artifacts[demo_name].image_path

    label, schema = _DEMO_OPTIONS[demo_name]
    status = (
        '<p><strong>已載入安全範例：</strong>'
        f"{escape(label)}。這是本機產生的合成文件，不含真實個資；"
        "文件類型也已自動設定。</p>"
    )
    return str(image_path), schema, status


def _gradio_demo_callback(
    demo_name: str | None,
) -> tuple[str, SchemaName, str]:
    try:
        return load_demo_document_callback(demo_name)
    except ValueError as exc:
        raise gr.Error(str(exc)) from None
    except RuntimeError:
        raise gr.Error(
            "無法建立合成範例，請稍後再試或改用自己的文件。"
        ) from None


def build_app(
    *,
    inspector: Inspector = inspect_document,
    request_guard: RequestGuard | None = None,
) -> gr.Blocks:
    """Build the local-only civic service desk interface without launching it."""

    def run_from_interface(
        file_path: str | None,
        schema_name: SchemaName,
        provider_name: ProviderName,
        cloud_consent: bool,
    ) -> Iterator[tuple[object, ...]]:
        yield from inspection_update_stream(
            file_path,
            schema_name,
            provider_name,
            cloud_consent,
            inspector=inspector,
            request_guard=request_guard,
        )

    with gr.Blocks(
        title="文件預檢所｜doc-inspector",
        fill_width=True,
        delete_cache=(600, 600),
        analytics_enabled=False,
    ) as app:
        gr.HTML(
            """<section class="masthead">
            <header class="app-header">
                <h1>文件預檢所</h1>
                <p>上傳填好的申請表或收據，送件前找出缺漏。</p>
            </header>
            <section class="result-legend" aria-labelledby="legend-title">
            <div class="legend-intro">
              <h2 id="legend-title">結果燈號</h2>
              <p>完成後照顏色處理</p>
            </div>
            <ul class="legend-items">
              <li class="legend-red">
                <span class="legend-dot legend-dot-red" aria-hidden="true"></span>
                <span class="legend-copy">
                  <strong>紅燈</strong>
                  <span class="legend-action">送件前先修正</span>
                </span>
              </li>
              <li class="legend-yellow">
                <span class="legend-dot legend-dot-yellow" aria-hidden="true"></span>
                <span class="legend-copy">
                  <strong>黃燈</strong>
                  <span class="legend-action">對照原文件確認</span>
                </span>
              </li>
              <li class="legend-green">
                <span class="legend-dot legend-dot-green" aria-hidden="true"></span>
                <span class="legend-copy">
                  <strong>綠燈</strong>
                  <span class="legend-action">目前未發現問題</span>
                </span>
              </li>
            </ul>
            </section>
            </section>"""
        )
        with gr.Column(elem_classes=["workbench"]):
            with gr.Column(elem_classes=["workflow-section", "upload-section"]):
                gr.HTML(
                    """<div class="task-heading">
                    <span class="task-step" aria-hidden="true">1</span>
                    <div class="task-heading-copy">
                      <h2>準備要檢查的文件</h2>
                      <p>請上傳已填好的申請表、店家收據或發票；不要選空白表格。</p>
                    </div>
                    </div>"""
                )
                gr.HTML(
                    """<section class="source-brief" aria-labelledby="source-brief-title">
                    <h3 id="source-brief-title">文件從哪裡來？</h3>
                    <p><strong>補助申請表：</strong>從承辦機關官網的
                    「補助公告／表單下載」取得，或洽承辦窗口。
                    <strong>收據／發票：</strong>使用店家提供的紙本或電子檔。</p>
                    </section>"""
                )
                document = gr.File(
                    label="選擇申請表、收據或發票",
                    file_types=[".png", ".jpg", ".jpeg", ".webp", ".pdf"],
                    type="filepath",
                    height=132,
                    elem_id="document-upload",
                    elem_classes=["upload-control"],
                )
                gr.HTML(
                    """<div class="upload-guidance" aria-label="上傳限制">
                    <span>PNG、JPEG、WebP、PDF</span>
                    <span>最大 25 MB</span>
                    <span>PDF 最多 10 頁</span>
                    </div>"""
                )
                with gr.Row(elem_classes=["demo-controls"]):
                    gr.HTML(
                        """<div class="demo-heading">
                        <h3>沒有文件？</h3>
                        <p>安全範例，不呼叫雲端。</p>
                        </div>""",
                        scale=2,
                        min_width=130,
                        elem_classes=["demo-heading-block"],
                    )
                    demo_selector = gr.Dropdown(
                        choices=[
                            (label, name)
                            for name, (label, _) in _DEMO_OPTIONS.items()
                        ],
                        value="receipt_green",
                        label="範例文件",
                        show_label=False,
                        scale=4,
                        elem_id="demo-selector",
                    )
                    load_demo_button = gr.Button(
                        "載入範例",
                        variant="secondary",
                        scale=2,
                        elem_id="load-demo",
                        elem_classes=["demo-btn"],
                    )
                demo_status = gr.HTML(
                    "",
                    elem_classes=["demo-status"],
                )
            with gr.Column(elem_classes=["workflow-section", "settings-section"]):
                gr.HTML(
                    """<div class="task-heading">
                    <span class="task-step" aria-hidden="true">2</span>
                    <div class="task-heading-copy">
                      <h2>確認預檢設定</h2>
                      <p>文件類型會決定檢查項目；雲端供應商會接收這份文件。</p>
                    </div>
                    </div>"""
                )
                with gr.Row(elem_classes=["control-grid"]):
                    schema = gr.Dropdown(
                        choices=[
                            ("補助申請表", "subsidy_application"),
                            ("收據／發票", "receipt"),
                        ],
                        value="subsidy_application",
                        label="文件類型",
                        elem_id="schema-selector",
                        elem_classes=["field-control"],
                    )
                    provider = gr.Dropdown(
                        choices=[("Gemini", "gemini"), ("OpenAI", "openai")],
                        value="gemini",
                        label="雲端供應商",
                        elem_id="provider-selector",
                        elem_classes=["field-control"],
                    )
            with gr.Column(elem_classes=["workflow-section", "action-section"]):
                gr.HTML(
                    """<div class="task-heading">
                    <span class="task-step" aria-hidden="true">3</span>
                    <div class="task-heading-copy">
                      <h2>確認傳送並開始</h2>
                      <p>閱讀告知、勾選同意，再按一次開始預檢。</p>
                    </div>
                    </div>"""
                )
                with gr.Row(elem_classes=["notice-grid"]):
                    gr.HTML(
                        """<div class="privacy-note"><strong>傳送與保存方式</strong>
                        <p>文件會送到你選擇的雲端供應商進行技術預檢。
                        工具不保存 raw API 回應，暫存檔會定期清除；
                        預檢結果不等於正式資格或法律判斷。</p>
                        </div>""",
                        scale=6,
                        min_width=260,
                        elem_classes=["privacy-block"],
                    )
                    consent = gr.Checkbox(
                        label="我了解並同意傳送這份文件",
                        info="只傳送給上方選擇的雲端供應商。",
                        scale=5,
                        min_width=240,
                        elem_id="cloud-consent",
                        elem_classes=["consent-control"],
                    )
                with gr.Row(equal_height=True, elem_classes=["action-grid"]):
                    inspect_button = gr.Button(
                        "開始預檢",
                        variant="primary",
                        scale=4,
                        min_width=180,
                        elem_classes=["primary-btn"],
                    )
                    status = gr.HTML(
                        '<div class="status-card"><strong>尚未開始</strong>'
                        '<p>上傳文件、確認設定並勾選同意後，即可開始。</p></div>',
                        scale=7,
                        min_width=300,
                        elem_classes=["status-output"],
                    )

        gr.HTML(
            """<div id="result-section" class="task-heading results-heading">
            <span class="task-step" aria-hidden="true">4</span>
            <div class="task-heading-copy">
              <h2>查看預檢結果</h2>
              <p>先照修正建議處理；需要時再查看辨識內容或全部檢核。</p>
            </div>
            </div>"""
        )
        action_plan = gr.HTML(
            """<section class="action-plan action-plan-empty"
            aria-labelledby="action-plan-title">
            <div class="action-plan-header">
              <div>
                <h3 id="action-plan-title">尚未產生修正建議</h3>
                <p>完成預檢後，這裡會依順序列出要修改或確認的項目。</p>
              </div>
            </div>
            </section>""",
            elem_id="action-plan",
        )
        with gr.Tabs(elem_classes=["result-tabs"]):
            with gr.Tab("辨識內容"):
                extraction = gr.HTML(
                    _result_table_html(
                        caption="辨識內容",
                        headers=_EXTRACTION_HEADERS,
                        rows=[],
                        table_class="extraction-result-table",
                    ),
                    elem_id="extraction-table",
                )
            with gr.Tab("全部檢核"):
                checks = gr.HTML(
                    _result_table_html(
                        caption="全部檢核",
                        headers=_CHECK_HEADERS,
                        rows=[],
                        table_class="checks-result-table",
                    ),
                    elem_id="checks-table",
                )
            with gr.Tab("JSON"):
                payload = gr.JSON(label="技術資料（InspectionBundle）")

        gr.HTML(
            """<div class="section-heading downloads-heading">
            <div class="section-heading-copy">
              <h3>下載結果</h3>
              <p>JSON 適合系統交換，Excel 適合人工檢閱與留存。</p>
            </div>
            </div>"""
        )
        with gr.Row(elem_classes=["download-row"]):
            json_file = gr.DownloadButton(
                "下載 JSON",
                value=None,
                variant="secondary",
                elem_classes=["download-control"],
            )
            excel_file = gr.DownloadButton(
                "下載 Excel",
                value=None,
                variant="secondary",
                elem_classes=["download-control"],
                )

        load_demo_button.click(
            fn=_gradio_demo_callback,
            inputs=[demo_selector],
            outputs=[document, schema, demo_status],
            api_visibility="private",
        )
        inspect_button.click(
            fn=run_from_interface,
            inputs=[document, schema, provider, consent],
            outputs=[
                status,
                action_plan,
                extraction,
                checks,
                payload,
                json_file,
                excel_file,
                inspect_button,
            ],
            show_progress="hidden",
            trigger_mode="once",
            concurrency_limit=1,
            concurrency_id="document-inspection",
            stream_every=0.05,
            api_visibility="private",
        )
    return app.queue(
        api_open=False,
        max_size=8,
        default_concurrency_limit=1,
    )


def launch() -> None:
    settings = load_settings()
    ensure_local_port_available(settings.gradio_server_port, settings.gradio_server_name)
    prepare_gradio_temp_root()
    request_limiter = HourlyRequestLimiter(settings.public_max_requests_per_hour)
    build_app(request_guard=request_limiter.check_and_record).launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=False,
        css=CIVIC_CSS,
        show_error=False,
        max_file_size=settings.max_file_bytes,
        max_threads=4,
        state_session_capacity=200,
        enable_monitoring=False,
    )
