"""Helpers for Next.js App Router pages.

Server components stream their props to the browser as
`self.__next_f.push([1, "<json string chunk>"])` script calls. The job data
a careers page renders is usually in there as plain JSON objects, so we can
read it from the raw HTML without a browser.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

flightPushPattern = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)', re.S)


def extractFlightText(html: str) -> str:
	chunks: list[str] = []
	for match in flightPushPattern.finditer(html):
		try:
			chunks.append(json.loads(match.group(1)))
		except json.JSONDecodeError:
			continue
	return "".join(chunks)


def findJsonObjects(text: str, requiredKeys: Iterable[str]) -> list[dict[str, Any]]:
	"""Finds every JSON object in `text` that contains all `requiredKeys`.

	Scans for '{"<firstKey>":' starts and decodes from there, so it works on
	the flight text where objects are embedded inside larger, non-JSON payloads.
	"""
	keys = list(requiredKeys)
	decoder = json.JSONDecoder()
	found: list[dict[str, Any]] = []
	seen: set[str] = set()
	for match in re.finditer(r'\{"', text):
		try:
			value, _ = decoder.raw_decode(text, match.start())
		except json.JSONDecodeError:
			continue
		if not isinstance(value, dict):
			continue
		if not all(key in value for key in keys):
			continue
		fingerprint = json.dumps(value, sort_keys=True)
		if fingerprint in seen:
			continue
		seen.add(fingerprint)
		found.append(value)
	return found
