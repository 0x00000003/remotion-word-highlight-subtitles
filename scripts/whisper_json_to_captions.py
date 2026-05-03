#!/usr/bin/env python3
"""Convert Whisper word-timestamp JSON into Remotion caption JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MERGE_TERMS = [
    "Codex",
    "ChatGPT",
    "Remotion",
    "Whisper",
    "提示词",
    "逐词",
    "高亮",
    "字幕",
    "手机",
    "照片",
    "视频",
    "封面",
]


def ms(value: float | int) -> int:
    return int(round(float(value) * 1000))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def parse_replacements(items: list[str]) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--replace must use OLD=NEW format: {item}")
        old, new = item.split("=", 1)
        replacements.append((old, new))
    return replacements


def apply_replacements(text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def term_matches(tokens: list[dict[str, Any]], index: int, term: str) -> int:
    combined = ""
    for cursor in range(index, len(tokens)):
        combined += tokens[cursor]["text"]
        if combined == term:
            return cursor - index + 1
        if not term.startswith(combined):
            return 0
    return 0


def merge_terms(
    tokens: list[dict[str, Any]],
    terms: list[str],
    keyword_terms: set[str],
) -> list[dict[str, Any]]:
    sorted_terms = sorted(set(terms), key=len, reverse=True)
    merged: list[dict[str, Any]] = []
    index = 0

    while index < len(tokens):
        matched_term = ""
        matched_count = 0
        for term in sorted_terms:
            count = term_matches(tokens, index, term)
            if count:
                matched_term = term
                matched_count = count
                break

        if matched_count:
            chunk = tokens[index : index + matched_count]
            merged.append(
                {
                    "text": matched_term,
                    "startMs": chunk[0]["startMs"],
                    "endMs": chunk[-1]["endMs"],
                    "keyword": matched_term in keyword_terms,
                }
            )
            index += matched_count
            continue

        token = dict(tokens[index])
        token["keyword"] = token["text"] in keyword_terms
        merged.append(token)
        index += 1

    return merged


def segment_tokens(
    segment: dict[str, Any],
    replacements: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for word in segment.get("words", []):
        raw_text = clean_text(str(word.get("word", "")))
        text = apply_replacements(raw_text, replacements)
        if not text:
            continue
        token = {
            "text": text,
            "startMs": ms(word.get("start", segment.get("start", 0))),
            "endMs": ms(word.get("end", segment.get("end", 0))),
        }
        if "probability" in word:
            token["confidence"] = word["probability"]
        tokens.append(token)
    return tokens


def convert(
    whisper_json: Path,
    output_json: Path,
    replacements: list[tuple[str, str]],
    merge_term_values: list[str],
    keyword_values: list[str],
) -> None:
    data = json.loads(whisper_json.read_text(encoding="utf-8"))
    keyword_terms = set(keyword_values)
    merge_term_values = list(dict.fromkeys([*merge_term_values, *keyword_values]))

    captions: list[dict[str, Any]] = []
    for segment in data.get("segments", []):
        text = apply_replacements(clean_text(str(segment.get("text", ""))), replacements)
        tokens = segment_tokens(segment, replacements)
        if not tokens:
            continue
        tokens = merge_terms(tokens, merge_term_values, keyword_terms)
        captions.append(
            {
                "text": text,
                "startMs": tokens[0]["startMs"],
                "endMs": tokens[-1]["endMs"],
                "tokens": tokens,
            }
        )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(captions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Whisper JSON with word timestamps to Remotion captions.json"
    )
    parser.add_argument("whisper_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        help="Text correction in OLD=NEW form. Can be repeated.",
    )
    parser.add_argument(
        "--merge-term",
        action="append",
        default=[],
        help="Adjacent token text to merge into one displayed token. Can be repeated.",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Terms to color as secondary keyword highlights. Can be repeated.",
    )
    parser.add_argument(
        "--no-default-merge-terms",
        action="store_true",
        help="Disable the built-in merge terms for common video/subtitle words.",
    )
    args = parser.parse_args()

    merge_terms_arg = [] if args.no_default_merge_terms else DEFAULT_MERGE_TERMS[:]
    merge_terms_arg.extend(args.merge_term)

    convert(
        args.whisper_json,
        args.output_json,
        parse_replacements(args.replace),
        merge_terms_arg,
        args.keyword,
    )


if __name__ == "__main__":
    main()
