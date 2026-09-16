"""서비스 스키마 로딩과 입력별 서비스 문맥(service_list_snippet) 구성.

원본: pipeline_common.py 의 스키마·문맥 구성 함수와
utils/retrieval_context.py 의 SimpleBM25 를 옮겼다. 원본은 connected_devices 가 있으면 그 장치
범주로 서비스 문맥을 만들고, 없으면 (1) 하이브리드 검색(bge-m3 dense + BM25) 결과, 또는
(2) 전체 스키마를 사용한다. 이 공개본은 (1) 중 BM25 경로만 제공하며 dense 임베딩 경로는
비공개 임베딩 번들과 파인튜닝 모델이 필요하므로 제공하지 않는다(docs/pipeline.md).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")


def load_service_schema(service_schema_path: str | Path) -> dict[str, dict[str, Any]]:
    with Path(service_schema_path).open(encoding="utf-8") as f:
        return json.load(f)


def canonical_service_name(device: str, service_name: str) -> str:
    return f"{device}_{service_name}"


def lowercase_output_member_name(member: str) -> str:
    return str(member or "").lower()


def unique_preserve_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)
    return ordered


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    normalized: list[str] = []
    for raw in raw_items:
        if raw is None:
            continue
        for token in str(raw).split(","):
            cleaned = token.strip()
            if cleaned:
                normalized.append(cleaned)
    return unique_preserve_order(normalized)


def resolve_schema_category(raw_category: Any, service_schema: dict[str, dict[str, Any]]) -> str:
    token = str(raw_category or "").strip()
    if not token:
        return ""
    if token in service_schema:
        return token
    lowered = token.casefold()
    for candidate in service_schema.keys():
        if candidate.casefold() == lowered:
            return candidate
    return ""


def build_service_record(category: str, service_name: str, meta: dict[str, Any]) -> dict[str, Any]:
    canonical_name = canonical_service_name(category, service_name)
    record = {
        "service": canonical_name,
        "raw_service": service_name,
        "canonical_name": canonical_name,
        "canonical_name_lower": lowercase_output_member_name(canonical_name),
        "type": meta.get("type", ""),
    }
    for key in (
        "argument_type",
        "argument_bounds",
        "argument_format",
        "argument_descriptor",
        "return_type",
        "return_bounds",
        "return_descriptor",
        "descriptor",
    ):
        value = meta.get(key)
        if value not in (None, "", []):
            record[key] = value

    enums_descriptor = meta.get("enums_descriptor") or []
    if enums_descriptor:
        enums: list[str] = []
        for raw in enums_descriptor:
            enum_text = str(raw).split(" - ", 1)[0].strip()
            if enum_text:
                enums.append(enum_text)
        if enums:
            record["enums"] = enums
    return record


def build_receiver_examples(category: str, selector_tags: list[str]) -> list[str]:
    examples = [f"(#{category})"]
    for tag in selector_tags:
        examples.append(f"(#{tag} #{category})")
    if len(selector_tags) > 1:
        examples.append("(" + " ".join(f"#{tag}" for tag in selector_tags + [category]) + ")")
    if selector_tags:
        examples.append("all(" + " ".join(f"#{tag}" for tag in selector_tags + [category]) + ")")
    else:
        examples.append(f"all(#{category})")
    return unique_preserve_order(examples)


def build_capability_binding(
    category: str,
    *,
    user_defined_tags: list[str],
    locations: list[str],
    service_schema: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selector_tags = unique_preserve_order(locations + user_defined_tags)
    services = service_schema.get(category, {})
    return {
        "category": category,
        "category_tag": f"#{category}",
        "user_defined_tags": user_defined_tags,
        "locations": locations,
        "selector_tags": selector_tags,
        "receiver_templates": [
            "(#<Category>)",
            "(#<selector_tag> #<Category>)",
            "(#<location> #<selector_tag> #<Category>)",
            "all(#<location> #<selector_tag> #<Category>)",
        ],
        "receiver_examples": build_receiver_examples(category, selector_tags),
        "services": [
            build_service_record(category, service_name, meta)
            for service_name, meta in sorted(services.items())
        ],
    }


def build_connected_device_groups(
    connected_devices: dict[str, Any],
    service_schema: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_id, meta in sorted(connected_devices.items(), key=lambda item: str(item[0])):
        raw_categories = normalize_string_list(meta.get("category"))
        resolved_categories: list[str] = []
        ignored_categories: list[str] = []
        for raw_category in raw_categories:
            category = resolve_schema_category(raw_category, service_schema)
            if category:
                resolved_categories.append(category)
            elif raw_category:
                ignored_categories.append(raw_category)
        resolved_categories = unique_preserve_order(resolved_categories)
        category_keys = {category.casefold() for category in resolved_categories}

        user_defined_tags = [
            tag
            for tag in normalize_string_list(meta.get("tags"))
            if tag.casefold() not in category_keys
        ]
        locations = [
            location
            for location in normalize_string_list(meta.get("locations"))
            if location.casefold() not in category_keys
        ]

        group_entry = {
            "group_id": str(group_id),
            "source": "connected_devices",
            "categories": resolved_categories,
            "user_defined_tags": user_defined_tags,
            "locations": locations,
            "capability_bindings": [
                build_capability_binding(
                    category,
                    user_defined_tags=user_defined_tags,
                    locations=locations,
                    service_schema=service_schema,
                )
                for category in resolved_categories
            ],
        }
        if ignored_categories:
            group_entry["ignored_categories"] = ignored_categories
        groups.append(group_entry)
    return groups


def build_schema_fallback_groups(service_schema: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "group_id": f"schema::{category}",
            "source": "service_schema_fallback",
            "categories": [category],
            "user_defined_tags": [],
            "locations": [],
            "capability_bindings": [
                build_capability_binding(
                    category,
                    user_defined_tags=[],
                    locations=[],
                    service_schema=service_schema,
                )
            ],
        }
        for category in sorted(service_schema.keys())
    ]


def build_retrieval_fallback_groups(
    shortlist: list[dict[str, Any]],
    *,
    service_schema: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    for hit in shortlist:
        category = resolve_schema_category(hit.get("device"), service_schema)
        if not category or category in seen_categories:
            continue
        seen_categories.add(category)
        groups.append(
            {
                "group_id": f"retrieval::{hit.get('rank', len(groups) + 1)}::{category}",
                "source": "service_retrieval_fallback",
                "categories": [category],
                "user_defined_tags": [],
                "locations": [],
                "retrieval_rank": int(hit.get("rank") or len(groups) + 1),
                "retrieval_score": round(float(hit.get("score") or 0.0), 6),
                "retrieval_dense_score": round(float(hit.get("dense_score") or 0.0), 6),
                "retrieval_bm25_score": round(float(hit.get("bm25_score") or 0.0), 6),
                "retrieval_info": str(hit.get("info", "") or ""),
                "capability_bindings": [
                    build_capability_binding(
                        category,
                        user_defined_tags=[],
                        locations=[],
                        service_schema=service_schema,
                    )
                ],
            }
        )
    return groups


# ---------------------------------------------------------------------------
# BM25 검색 경로 (원본 retrieval_context.SimpleBM25; numpy 없이 같은 계산)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(str(text))]


class SimpleBM25:
    """원본 SimpleBM25 와 같은 계산. 점수 누적만 float64(원본은 numpy float32)라 동점 근처 순위가 다를 수 있다."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.corpus_size = len(corpus)
        self.avgdl = 0.0
        self.doc_freqs: list[Counter[str]] = []
        self.idf: dict[str, float] = {}
        self.doc_len: list[int] = []
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self._initialize()

    def _initialize(self) -> None:
        total_len = 0
        df: dict[str, int] = {}
        for doc in self.corpus:
            tokens = _tokenize(doc)
            self.doc_len.append(len(tokens))
            total_len += len(tokens)
            freqs = Counter(tokens)
            self.doc_freqs.append(freqs)
            for token in freqs:
                df[token] = df.get(token, 0) + 1

        self.avgdl = (total_len / self.corpus_size) if self.corpus_size else 0.0
        for token, freq in df.items():
            self.idf[token] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query: str) -> list[float]:
        scores = [0.0] * self.corpus_size
        for token in _tokenize(query):
            idf = self.idf.get(token)
            if idf is None:
                continue
            for idx, doc_freqs in enumerate(self.doc_freqs):
                freq = doc_freqs.get(token, 0)
                if freq <= 0:
                    continue
                numerator = idf * freq * (self.k1 + 1)
                denominator = freq + self.k1 * (1 - self.b + self.b * self.doc_len[idx] / (self.avgdl + 1e-9))
                scores[idx] += numerator / denominator
        return scores


class Bm25Retriever:
    """서비스 범주 설명 문서(schemas/service_retrieval_corpus.json)에 대한 BM25 검색."""

    def __init__(self, corpus_path: str | Path):
        payload = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        self.doc_ids = [str(item) for item in payload["keys"]]
        self.texts = [str(item) for item in payload["texts"]]
        if len(self.doc_ids) != len(self.texts):
            raise ValueError("retrieval corpus keys/texts length mismatch")
        self.bm25 = SimpleBM25(self.texts)

    def search(self, query: str, *, topk: int = 10) -> list[dict[str, Any]]:
        scores = self.bm25.get_scores(query)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[: max(1, int(topk))]
        return [
            {
                "rank": rank,
                "device": self.doc_ids[idx],
                "score": float(scores[idx]),
                "dense_score": 0.0,
                "bm25_score": float(scores[idx]),
                "info": "",
            }
            for rank, idx in enumerate(order, start=1)
        ]


def mandatory_retrieval_categories(command_text: str) -> list[str]:
    """명령 문구에서 반드시 포함할 범주(원본 _mandatory_retrieval_categories)."""
    text = str(command_text or "").lower()
    categories: list[str] = []
    has_outdoor = any(token in text for token in ("outdoor", "outside", "external", "외부", "바깥"))
    has_air_quality = any(
        token in text
        for token in (
            "dust",
            "fine dust",
            "pm10",
            "pm2.5",
            "pm25",
            "air quality",
            "미세먼지",
            "초미세먼지",
            "공기질",
        )
    )
    if has_outdoor and has_air_quality:
        categories.append("WeatherProvider")
    if has_air_quality:
        categories.extend(["AirQualitySensor", "WeatherProvider"])

    has_rain_recheck = (
        any(token in text for token in ("rain", "raining", "비"))
        and any(token in text for token in ("check again", "recheck", "again after", "다시 체크", "체크해서"))
        and any(token in text for token in ("not raining", "isn't raining", "비가 안", "비 안"))
    )
    if has_rain_recheck:
        categories.extend(["RainSensor", "WeatherProvider"])
    if any(token in text for token in ("humidity", "humid", "습도")):
        categories.append("HumiditySensor")
    if any(token in text for token in ("temperature", "온도")) and not has_outdoor:
        categories.append("TemperatureSensor")
    if any(token in text for token in ("illuminance", "lux", "조도")):
        categories.append("LightSensor")
    if any(token in text for token in ("person", "presence", "occupancy", "someone", "no one", "detected", "사람", "재실", "감지")):
        categories.append("PresenceSensor")
    if any(token in text for token in ("speaker", "announce", "notify", "output", "speak", "say", "스피커", "알려", "출력", "말해")):
        categories.append("Speaker")
    if any(token in text for token in ("rain", "raining", "비")):
        categories.append("RainSensor")
    if any(token in text for token in ("carbon dioxide", "co2", "이산화탄소")):
        categories.extend(["AirQualitySensor", "CarbonDioxideSensor"])
    if any(token in text for token in ("blind", "window", "shade", "curtain", "블라인드", "창문", "커튼", "쉐이드")):
        categories.extend(["WindowCovering", "ArmRobot"])
    if any(token in text for token in ("siren", "alarm", "사이렌", "경보", "알람")):
        categories.append("Siren")
    if any(token in text for token in ("door", "문")):
        categories.append("Door")
    if any(token in text for token in ("camera", "photo", "picture", "image", "카메라", "사진")):
        categories.append("Camera")
    if any(token in text for token in (
        "every ", "minute", "hourly", " am", " pm", "a.m.", "p.m.", "midnight", "noon",
        "weekday", "weekend", "o'clock", "매일", "매시간", "시마다", "분마다",
    )):
        categories.append("Clock")
    if any(token in text for token in (
        "turn on", "turn off", "turn it on", "turn it off", "switch on", "switch off",
        "power on", "power off", "켜", "꺼",
    )) or re.search(r"for \d+ (?:second|minute|hour)", text):
        categories.append("Switch")
    return categories


def with_mandatory_retrieval_hits(
    shortlist: list[dict[str, Any]],
    mandatory_categories: list[str],
    *,
    service_schema: dict[str, dict[str, Any]],
    topk: int,
) -> list[dict[str, Any]]:
    if not mandatory_categories:
        return shortlist
    max_score = max((float(hit.get("score") or 0.0) for hit in shortlist), default=0.0)
    boosted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset, category in enumerate(mandatory_categories):
        resolved = resolve_schema_category(category, service_schema)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        boosted.append(
            {
                "device": resolved,
                "rank": len(boosted) + 1,
                "score": max_score + 1.0 + (len(mandatory_categories) - offset) * 0.001,
                "dense_score": 0.0,
                "bm25_score": 0.0,
                "info": "mandatory_command_semantics",
            }
        )
    for hit in shortlist:
        resolved = resolve_schema_category(hit.get("device"), service_schema)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        item = dict(hit)
        item["device"] = resolved
        boosted.append(item)
    limited = boosted[: max(int(topk or len(boosted)), len(mandatory_categories))]
    for rank, hit in enumerate(limited, start=1):
        hit["rank"] = rank
    return limited


CANONICAL_RULE = (
    "Resolve schema matches against canonical_name. "
    "In final JOILang code, write every receiver tag after # with an uppercase first letter, "
    "canonical service-category tags exactly as listed in the schema, "
    "but lowercase the member token after ). or all(...). . "
    "For example, #bedroom becomes #Bedroom, #temperaturesensor becomes #TemperatureSensor, "
    "and Switch_On becomes switch_on."
)
BINDING_RULE = [
    "Each device_group is one connected-device group, one retrieval fallback group, or one schema fallback group.",
    "Each capability_binding pairs one category with the full authoritative service list for that category.",
    "user_defined_tags come from tags after removing category duplicates.",
    "locations are additional selector tags that can also be combined with the category.",
    "selector_tags are the usable extra tags that may be prepended before the category in a receiver.",
    "If the command does not mention any selector tag, the base receiver (#Category) is valid.",
    "If the command mentions locations or custom tags, preserve only the relevant selector tags before the category.",
    "If snippet_source is service_retrieval_fallback, use only the retrieved categories present in device_groups.",
]

CONTEXT_MODES = ("schema_fallback", "bm25_fallback")


def build_service_snippet_payload(
    command_text: str,
    connected_devices: dict[str, Any],
    service_schema: dict[str, dict[str, Any]],
    *,
    context_mode: str = "schema_fallback",
    retriever: Bm25Retriever | None = None,
    retrieval_topk: int = 10,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """입력별 서비스 문맥.

    connected_devices 가 있으면 그 장치 범주만 사용한다(검색 생략). 없으면 context_mode 에 따라
    전체 스키마(schema_fallback) 또는 BM25 shortlist + 필수 범주(bm25_fallback)를 사용한다.
    """
    if context_mode not in CONTEXT_MODES:
        raise ValueError(f"context_mode must be one of {CONTEXT_MODES}")
    snippet_source = "connected_devices_only"
    # 원본은 검색을 쓰지 않을 때도 설정값(mode=hybrid, device=cpu)을 메타데이터로 남긴다.
    # 조립 결과가 원본과 바이트 단위로 같도록 같은 필드를 기록한다(공개본은 dense 검색을 수행하지 않는다).
    retrieval_info: dict[str, Any] = {
        "enabled": context_mode == "bm25_fallback",
        "mode": "bm25" if context_mode == "bm25_fallback" else "hybrid",
        "topk": retrieval_topk,
        "device": "cpu",
        "status": "not_used",
        "categories": [],
        "scores": [],
        "fallback_reason": "",
    }

    if connected_devices:
        device_groups = build_connected_device_groups(connected_devices, service_schema)
        retrieval_info["status"] = "skipped_connected_devices_present"
    elif context_mode == "bm25_fallback":
        if retriever is None:
            raise ValueError("bm25_fallback requires a Bm25Retriever")
        snippet_source = "service_schema_fallback"
        shortlist = retriever.search(command_text or "", topk=retrieval_topk)
        shortlist = with_mandatory_retrieval_hits(
            shortlist,
            mandatory_retrieval_categories(command_text),
            service_schema=service_schema,
            topk=retrieval_topk,
        )
        retrieval_groups = build_retrieval_fallback_groups(shortlist, service_schema=service_schema)
        if retrieval_groups:
            device_groups = retrieval_groups
            snippet_source = "service_retrieval_fallback"
            retrieval_info["status"] = "used"
            retrieval_info["categories"] = [group["categories"][0] for group in retrieval_groups]
            retrieval_info["scores"] = [group.get("retrieval_score", 0.0) for group in retrieval_groups]
        else:
            device_groups = build_schema_fallback_groups(service_schema)
            retrieval_info["status"] = "empty_shortlist"
            retrieval_info["fallback_reason"] = "retrieval returned no supported categories"
    else:
        snippet_source = "service_schema_fallback"
        device_groups = build_schema_fallback_groups(service_schema)
        retrieval_info["status"] = "disabled"

    snippet: dict[str, Any] = {
        "snippet_source": snippet_source,
        "retrieval": retrieval_info,
        "canonical_rule": CANONICAL_RULE,
        "binding_rule": list(BINDING_RULE),
        "device_groups": device_groups,
    }
    snippet_meta = {
        "service_list_snippet_source": snippet_source,
        "service_list_device_count": len(device_groups),
        "service_list_retrieval_status": retrieval_info.get("status", ""),
        "service_list_retrieval_mode": retrieval_info.get("mode", ""),
        "service_list_retrieval_topk": retrieval_info.get("topk", 0),
        "service_list_retrieval_device": retrieval_info.get("device", ""),
        "service_list_retrieval_categories": json.dumps(retrieval_info.get("categories", []), ensure_ascii=False),
        "service_list_retrieval_scores": json.dumps(retrieval_info.get("scores", []), ensure_ascii=False),
        "service_list_retrieval_fallback_reason": str(retrieval_info.get("fallback_reason", "") or ""),
    }
    return snippet, snippet_meta


def function_member_names_from_schema(service_schema: dict[str, Any] | None) -> set[str]:
    if not service_schema:
        return set()
    names: set[str] = set()
    for device_name, services in service_schema.items():
        if not isinstance(services, dict):
            continue
        for service_name, metadata in services.items():
            if not isinstance(metadata, dict):
                continue
            if str(metadata.get("type", "")).strip().lower() != "function":
                continue
            names.add(lowercase_output_member_name(canonical_service_name(str(device_name), str(service_name))))
    return names
