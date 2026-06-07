#!/usr/bin/env python3
"""Manual 3DGS knowledge-base workflow for an Obsidian vault."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "3dgs-obsidian-kb/0.1 (local research workflow)"

SEARCH_PROFILES = {
    "3dgs-editing": [
        "3D Gaussian Splatting editing",
        "Gaussian Splatting editing",
        "3DGS editing",
        "Gaussian Splatting scene editing",
        "Gaussian Splatting manipulation",
        "editable 3D Gaussian Splatting",
        "text-guided 3DGS editing",
        "text-driven Gaussian Splatting editing",
        "instruction-guided 3D Gaussian Splatting",
        "language-guided 3DGS editing",
        "local 3DGS editing",
        "object-level Gaussian Splatting editing",
        "3DGS object removal",
        "3DGS object insertion",
        "3DGS scene manipulation",
        "semantic 3DGS editing",
        "Gaussian Splatting segmentation",
        "3DGS scene decomposition",
        "object-aware 3D Gaussian Splatting",
        "instance-level 3DGS editing",
        "3DGS stylization",
        "Gaussian Splatting style transfer",
        "appearance editing 3D Gaussian Splatting",
        "texture editing Gaussian Splatting",
        "material editing 3DGS",
        "geometry editing 3D Gaussian Splatting",
        "deformation 3D Gaussian Splatting",
        "shape editing 3DGS",
        "dynamic Gaussian Splatting editing",
    ],
    "3d-scene-editing": [
        "3D Gaussian Splatting editing",
        "3DGS editing",
        "Gaussian Splatting scene editing",
        "Gaussian Splatting manipulation",
        "editable 3D Gaussian Splatting",
        "text-guided 3DGS editing",
        "text-driven Gaussian Splatting editing",
        "instruction-guided 3D Gaussian Splatting",
        "language-guided 3DGS editing",
        "local 3DGS editing",
        "object-level Gaussian Splatting editing",
        "3DGS object removal",
        "3DGS object insertion",
        "3DGS scene manipulation",
        "semantic 3DGS editing",
        "Gaussian Splatting segmentation",
        "3DGS scene decomposition",
        "object-aware 3D Gaussian Splatting",
        "instance-level 3DGS editing",
        "3DGS stylization",
        "Gaussian Splatting style transfer",
        "appearance editing 3D Gaussian Splatting",
        "texture editing Gaussian Splatting",
        "material editing 3DGS",
        "geometry editing 3D Gaussian Splatting",
        "deformation 3D Gaussian Splatting",
        "shape editing 3DGS",
        "dynamic Gaussian Splatting editing",
    ],
}

GS_TERMS = [
    "3d gaussian splatting",
    "gaussian splatting",
    "3dgs",
    "gaussian splat",
]

SCENE_EDITING_KEYWORD_GROUPS = {
    "core_editing": [
        "3d gaussian splatting editing",
        "3dgs editing",
        "gaussian splatting scene editing",
        "gaussian splatting manipulation",
        "editable 3d gaussian splatting",
        "3d editing with gaussian splatting",
        "controllable 3d editing with gaussian",
        "editing on gaussian splatting",
        "editing with gaussian splatting",
        "gaussian splatting for editing",
    ],
    "text_guided": [
        "text-guided 3dgs editing",
        "text-driven gaussian splatting editing",
        "instruction-guided 3d gaussian splatting",
        "language-guided 3dgs editing",
        "instruction-driven editing",
        "language-driven 3dgs editing",
        "language-driven gaussian splatting editing",
    ],
    "local_object": [
        "local 3dgs editing",
        "object-level gaussian splatting editing",
        "3dgs object removal",
        "3dgs object insertion",
        "3dgs scene manipulation",
        "multi-object 3d gaussian splatting",
        "inpainting 3d gaussian splatting",
        "inpainting gaussian splatting",
    ],
    "semantic_decomposition": [
        "semantic 3dgs editing",
        "gaussian splatting segmentation",
        "3dgs scene decomposition",
        "object-aware 3d gaussian splatting",
        "instance-level 3dgs editing",
        "referring segmentation in 3d gaussian splatting",
        "3d referential segmentation",
        "semantic editing",
        "scene decomposition",
        "instance-level 3dgs",
        "instance level 3dgs",
    ],
    "appearance_style": [
        "3dgs stylization",
        "gaussian splatting style transfer",
        "appearance editing 3d gaussian splatting",
        "texture editing gaussian splatting",
        "material editing 3dgs",
        "stylization",
        "style transfer",
        "appearance editing",
        "texture editing",
        "material editing",
    ],
    "geometry": [
        "geometry editing 3d gaussian splatting",
        "deformation 3d gaussian splatting",
        "shape editing 3dgs",
        "dynamic gaussian splatting editing",
        "geometry editing",
        "shape editing",
    ],
}

TAG_RULES = {
    "scene-editing": SCENE_EDITING_KEYWORD_GROUPS["core_editing"],
    "text-guided": SCENE_EDITING_KEYWORD_GROUPS["text_guided"],
    "local-editing": SCENE_EDITING_KEYWORD_GROUPS["local_object"],
    "semantic": SCENE_EDITING_KEYWORD_GROUPS["semantic_decomposition"],
    "appearance": SCENE_EDITING_KEYWORD_GROUPS["appearance_style"],
    "geometry": SCENE_EDITING_KEYWORD_GROUPS["geometry"],
}

DEFAULT_CVF_VENUES = ["CVPR2026", "CVPR2025", "CVPR2024", "ICCV2025", "ICCV2023"]
DEFAULT_OPENREVIEW_VENUES = ["NeurIPS.cc/2025/Conference", "NeurIPS.cc/2024/Conference"]
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEP_READ_MAX_CHARS = 80000
PDF_TEXT_TOOL_VALUES = ["auto", "mineru-api", "mineru-precise", "mineru-agent", "mineru", "pdftotext", "mutool"]
FIGURE_SOURCE_VALUES = ["mineru-first", "mineru", "pymupdf"]
FIGURE_FOCUS_VALUES = ["overview", "broad"]
FIGURE_SOURCE_KEYS = {"image", "figure", "chart", "table"}
OVERVIEW_FIGURE_TERMS = [
    "architecture",
    "framework",
    "pipeline",
    "overview",
    "method overview",
    "overall",
    "system",
    "workflow",
    "network architecture",
    "model architecture",
    "模型架构",
    "模型结构",
    "方法总览",
    "方法框架",
    "整体架构",
    "系统框架",
    "流程图",
]
KEY_FIGURE_TERMS = [
    "architecture",
    "framework",
    "pipeline",
    "overview",
    "method",
    "network",
    "model",
    "system",
    "workflow",
    "fig. 1",
    "fig. 2",
    "figure 1",
    "figure 2",
    "架构",
    "框架",
    "流程",
    "方法总览",
    "模型结构",
    "网络结构",
]
LOW_VALUE_FIGURE_TERMS = [
    "qualitative",
    "comparison",
    "result",
    "ablation",
    "user study",
    "定性",
    "对比",
    "结果",
    "消融",
]

READING_STATUS_VALUES = ["candidate", "queued", "reading", "read", "skipped"]
PRIORITY_VALUES = ["A", "B", "C"]

LEGACY_READING_QUESTIONS = [
    "这篇文章解决的具体编辑问题是什么？",
    "方法和现有 3DGS pipeline 的接口在哪里？",
    "对我的研究方向有什么可复用的实验或评估指标？",
]

DEFAULT_READING_QUESTIONS = [
    "这篇文章解决的具体编辑问题是什么？是文本驱动、局部物体编辑、外观编辑、几何编辑，还是删除/插入？",
    "方法和现有 3DGS pipeline 的接口在哪里？改的是 Gaussian 表示、训练损失、渲染过程、语义标签，还是后处理流程？",
    "它需要哪些额外输入？例如文本 prompt、2D mask、多视角图像、深度、语义分割、预训练模型。",
    "它和已有方法相比，真正的新点是什么？是更快、更稳、更可控，还是支持了新的编辑类型？",
    "实验主要证明了什么？有没有和 NeRF 编辑、Instruct-NeRF2NeRF、GaussianEditor 等方法比较？",
    "使用了哪些评价指标？例如 CLIP 相似度、用户偏好、编辑时间、几何一致性、多视角一致性。",
    "失败案例或局限是什么？比如小物体、遮挡、多视角不一致、prompt 不稳定、需要人工 mask。",
    "对我的研究方向有什么可复用的实验、指标、模块或写法？",
]


def question_list_body(questions: list[str]) -> str:
    return "".join(f"- {question}\n" for question in questions)


def read_after_question_body(questions: list[str]) -> str:
    return "".join(f"- 待精读后回答：{question}\n" for question in questions)


READING_DETAIL_SECTIONS = [
    ("核心问题", "待补充：这篇论文到底解决什么具体问题？\n"),
    ("方法一句话", "待补充：用一句普通话说清楚方法，不照抄论文标题。\n"),
    ("输入输出", "- 输入：待补充\n- 输出：待补充\n"),
    ("关键模块", "- 待补充：方法分几步，每一步做什么。\n"),
    ("实验设置", "- 数据集：待补充\n- Baseline：待补充\n- 指标：待补充\n"),
    ("主要结论", "- 待补充：作者证明了什么，哪些结论最重要。\n"),
    ("局限/风险", "- 待补充：没解决什么，哪些地方可能不稳。\n"),
    ("和我方向的关系", "- 可借鉴：待补充\n- 不适合直接借鉴：待补充\n"),
    ("可复用点", "- 代码：待确认\n- 指标：待补充\n- 实验设计：待补充\n- 图表/写法：待补充\n"),
    (
        "读后问题回答",
        read_after_question_body(DEFAULT_READING_QUESTIONS),
    ),
]

TASK_LABELS = {
    "text-guided": "文本/语言驱动编辑",
    "local-editing": "局部/物体级编辑",
    "semantic": "语义分割/场景解耦",
    "appearance": "外观/风格编辑",
    "geometry": "几何/形变编辑",
    "scene-editing": "通用 3DGS 编辑",
}


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def today() -> str:
    return dt.date.today().isoformat()


def ensure_dirs(vault: Path) -> None:
    for name in ["Papers", "Indexes", "Reports", "Scripts", "data"]:
        (vault / name).mkdir(parents=True, exist_ok=True)


def load_env_file(vault: Path) -> None:
    env_path = vault / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def http_get(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def http_get_text(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> str:
    return http_get(url, params=params, timeout=timeout).decode("utf-8", errors="replace")


def http_get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    return json.loads(http_get_text(url, params=params, timeout=timeout))


def normalize_title(title: str) -> str:
    title = html.unescape(title or "")
    title = re.sub(r"\s+", " ", title).strip().lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def canonical_title(title: str) -> str:
    text = normalize_title(title)
    replacements = {
        "three d": "3d",
        "3 d": "3d",
        "models": "model",
        "splats": "splat",
        "gaussians": "gaussian",
    }
    for src, dst in replacements.items():
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text)
    weak_terms = {
        "model",
        "models",
        "paper",
        "framework",
        "method",
        "approach",
    }
    tokens = [token for token in text.split() if token not in weak_terms]
    return " ".join(tokens)


def title_similarity(left: str, right: str) -> float:
    left_canon = canonical_title(left)
    right_canon = canonical_title(right)
    if not left_canon or not right_canon:
        return 0.0
    if left_canon == right_canon:
        return 1.0
    left_tokens = set(left_canon.split())
    right_tokens = set(right_canon.split())
    token_score = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    prefix_score = 0.0
    shorter, longer = sorted([left_canon, right_canon], key=len)
    if longer.startswith(shorter) and len(shorter) >= 24:
        prefix_score = len(shorter) / len(longer)
    return max(token_score, prefix_score)


def is_similar_title(left: str, right: str, threshold: float = 0.88) -> bool:
    return title_similarity(left, right) >= threshold


def slugify(title: str, limit: int = 80) -> str:
    normalized = normalize_title(title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return (slug[:limit].strip("-") or "paper")


def stable_key(paper: dict[str, Any]) -> str:
    ids = paper.get("ids") or {}
    for field in ["arxiv", "doi", "semantic_scholar"]:
        value = ids.get(field)
        if value:
            return f"{field}:{str(value).lower()}"
    title_key = normalize_title(paper.get("title", ""))
    digest = hashlib.sha1(title_key.encode("utf-8")).hexdigest()[:12]
    return f"title:{digest}"


def normalize_text(text: str) -> str:
    text = html.unescape(text or "").lower()
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_any_phrase(text: str, phrases: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(phrase) in normalized for phrase in phrases)


def scene_editing_relevance(title: str, abstract: str = "") -> dict[str, Any]:
    text = f"{title} {abstract}"
    has_gs = has_any_phrase(text, GS_TERMS)
    matched_groups = [
        group
        for group, terms in SCENE_EDITING_KEYWORD_GROUPS.items()
        if has_any_phrase(text, terms)
    ]
    title_has_edit = any(has_any_phrase(title, terms) for terms in SCENE_EDITING_KEYWORD_GROUPS.values())
    exact_phrase_hit = has_any_phrase(text, SEARCH_PROFILES["3d-scene-editing"])
    # Keep papers that are clearly about Gaussian Splatting scene editing.
    # A plain rendering/reconstruction/SLAM 3DGS paper is not enough.
    is_relevant = has_gs and (exact_phrase_hit or title_has_edit or bool(matched_groups))
    return {
        "is_relevant": is_relevant,
        "has_gs": has_gs,
        "matched_groups": matched_groups,
        "exact_phrase_hit": exact_phrase_hit,
        "title_has_edit": title_has_edit,
    }


def contains_related_text(title: str, abstract: str = "") -> bool:
    return bool(scene_editing_relevance(title, abstract)["is_relevant"])


def contains_gs_text(title: str, abstract: str = "") -> bool:
    return has_any_phrase(f"{title} {abstract}", GS_TERMS)


def infer_tags(title: str, abstract: str = "") -> list[str]:
    text = f"{title} {abstract}"
    tags = ["paper", "3dgs", "3d-scene-editing"]
    for tag, terms in TAG_RULES.items():
        if has_any_phrase(text, terms):
            tags.append(tag)
    return sorted(set(tags))


def short_comment(title: str, abstract: str, tags: list[str]) -> str:
    parts = []
    if "scene-editing" in tags:
        parts.append("和 3DGS 场景编辑/可控修改直接相关")
    if "text-guided" in tags:
        parts.append("涉及文本、语言或指令驱动编辑")
    if "local-editing" in tags:
        parts.append("涉及局部编辑、物体插入/删除或场景操作")
    if "semantic" in tags:
        parts.append("涉及语义分割、实例级理解或场景解耦")
    if "appearance" in tags:
        parts.append("涉及风格、外观、纹理或材质编辑")
    if "geometry" in tags:
        parts.append("涉及几何、形变、形状或动态编辑")
    if not parts:
        parts.append("包含 3DGS 场景编辑相关线索")
    return "；".join(parts) + "。"


def paper_text(paper: dict[str, Any]) -> str:
    return f"{paper.get('title', '')} {paper.get('abstract', '')}"


def infer_priority(paper: dict[str, Any]) -> str:
    tags = set(paper.get("tags") or infer_tags(paper.get("title", ""), paper.get("abstract", "")))
    venue = str(paper.get("venue") or "").upper()
    title_abstract = normalize_text(paper_text(paper))
    direct_terms = [
        "editing",
        "editor",
        "manipulation",
        "object removal",
        "object insertion",
        "language driven",
        "text driven",
        "instruction driven",
    ]
    if (
        "scene-editing" in tags
        and ("CVPR" in venue or "ICCV" in venue or has_any_phrase(title_abstract, direct_terms))
    ):
        return "A"
    if tags & {"text-guided", "local-editing", "semantic", "appearance", "geometry"}:
        return "B"
    return "C"


def infer_task_labels(paper: dict[str, Any]) -> list[str]:
    tags = set(paper.get("tags") or infer_tags(paper.get("title", ""), paper.get("abstract", "")))
    labels = [label for tag, label in TASK_LABELS.items() if tag in tags]
    text = paper_text(paper)
    if has_any_phrase(text, ["watermark", "ownership", "adversarial", "safeguard", "deterrence"]):
        labels.append("安全/水印/防篡改")
    return labels or ["待分类"]


def infer_method_clues(paper: dict[str, Any]) -> list[str]:
    text = paper_text(paper)
    clues = []
    rules = [
        ("2D diffusion / inpainting guidance", ["diffusion", "generative guidance", "inpainter", "inpainting"]),
        ("semantic field / prototype / transport", ["semantic field", "embedding field", "prototype", "transport"]),
        ("mask / segmentation", ["segmentation", "mask", "grounding"]),
        ("multi-view consistency / alignment", ["multi view", "multi-view", "cross view", "cross-view", "consistency", "view alignment"]),
        ("geometry alignment / mesh / deformation", ["geometry", "mesh", "deformation", "shape"]),
        ("MLLM / agent workflow", ["mllm", "agent"]),
        ("opacity / primitive modeling", ["opacity", "primitive"]),
    ]
    for label, terms in rules:
        if has_any_phrase(text, terms):
            clues.append(label)
    return clues or ["待精读确认"]


def extract_code_hint(paper: dict[str, Any]) -> str:
    text = paper.get("abstract") or ""
    match = re.search(r"https?://\S+", text)
    if match:
        return match.group(0).rstrip(".,)")
    return "待确认"


def section_exists(content: str, title: str) -> bool:
    return re.search(rf"^##\s+{re.escape(title)}\s*$", content, flags=re.MULTILINE) is not None


def reading_template_sections(paper: dict[str, Any]) -> list[tuple[str, str]]:
    status = paper.get("reading_status") or paper.get("status") or "candidate"
    priority = paper.get("priority") or infer_priority(paper)
    return [
        ("精读状态", f"- 阅读状态：{status}\n- 优先级：{priority}\n- PDF 精读：未开始\n"),
        *READING_DETAIL_SECTIONS,
    ]


def sync_reading_status_section(content: str, paper: dict[str, Any]) -> str:
    status = paper.get("reading_status") or paper.get("status") or "candidate"
    priority = paper.get("priority") or infer_priority(paper)
    match = re.search(r"(^##\s+精读状态\s*$)(?P<body>.*?)(?=^##\s+|\Z)", content, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return content
    body = match.group("body")
    body = re.sub(r"^- 阅读状态：.*$", f"- 阅读状态：{status}", body, flags=re.MULTILINE)
    body = re.sub(r"^- 优先级：.*$", f"- 优先级：{priority}", body, flags=re.MULTILINE)
    return content[: match.start("body")] + body + content[match.end("body") :]


def frontmatter_bounds(content: str) -> tuple[int, int] | None:
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---", 4)
    if end == -1:
        return None
    return (0, end + 4)


def ensure_frontmatter_field(content: str, key: str, value: str) -> str:
    bounds = frontmatter_bounds(content)
    if not bounds:
        return content
    start, end = bounds
    frontmatter = content[start:end]
    if re.search(rf"^{re.escape(key)}\s*:", frontmatter, flags=re.MULTILINE):
        return content
    insert_at = frontmatter.find("\n---")
    quoted = yaml_quote(value)
    updated_frontmatter = frontmatter[:insert_at] + f"\n{key}: {quoted}" + frontmatter[insert_at:]
    return updated_frontmatter + content[end:]


def set_frontmatter_field(content: str, key: str, value: str) -> str:
    bounds = frontmatter_bounds(content)
    if not bounds:
        return content
    start, end = bounds
    frontmatter = content[start:end]
    quoted = yaml_quote(value)
    pattern = rf"^{re.escape(key)}\s*:.*$"
    if re.search(pattern, frontmatter, flags=re.MULTILINE):
        frontmatter = re.sub(pattern, f"{key}: {quoted}", frontmatter, count=1, flags=re.MULTILINE)
    else:
        insert_at = frontmatter.find("\n---")
        frontmatter = frontmatter[:insert_at] + f"\n{key}: {quoted}" + frontmatter[insert_at:]
    return frontmatter + content[end:]


def ensure_reading_template(content: str, paper: dict[str, Any]) -> str:
    content = ensure_frontmatter_field(content, "reading_status", paper.get("reading_status") or paper.get("status") or "candidate")
    content = ensure_frontmatter_field(content, "priority", paper.get("priority") or infer_priority(paper))
    content = sync_reading_status_section(content, paper)
    content = ensure_default_reading_questions(content)
    content = ensure_default_read_after_questions(content)
    for title, body in reading_template_sections(paper):
        if not section_exists(content, title):
            if title == "读后问题回答" and section_exists(content, "精读可信度"):
                content = insert_markdown_section_before(content, "精读可信度", title, body)
            else:
                content = replace_markdown_section(content, title, body)
    return content


def extract_frontmatter_value(content: str, key: str) -> str:
    bounds = frontmatter_bounds(content)
    if not bounds:
        return ""
    frontmatter = content[bounds[0] : bounds[1]]
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.+?)\s*$", frontmatter, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip().strip("\"'")


def markdown_section_body(content: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$\n?(?P<body>.*?)(?=^##\s+|\Z)", content, flags=re.MULTILINE | re.DOTALL)
    return match.group("body").strip() if match else ""


def extract_reading_questions(content: str) -> list[str]:
    body = markdown_section_body(content, "待读问题")
    questions = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if match:
            question = match.group(1).strip()
            if question:
                questions.append(question)
    return questions


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", "", question.strip())


def is_legacy_reading_questions(questions: list[str]) -> bool:
    return [normalize_question(question) for question in questions] == [
        normalize_question(question) for question in LEGACY_READING_QUESTIONS
    ]


def ensure_default_reading_questions(content: str) -> str:
    questions = extract_reading_questions(content)
    if not questions or is_legacy_reading_questions(questions):
        return replace_markdown_section(content, "待读问题", question_list_body(DEFAULT_READING_QUESTIONS))
    return content


def ensure_default_read_after_questions(content: str) -> str:
    body = markdown_section_body(content, "读后问题回答")
    if not body:
        return content
    questions = []
    for line in body.splitlines():
        line = line.strip()
        match = re.match(r"^- 待精读后回答：(.+)$", line)
        if match:
            questions.append(match.group(1).strip())
    if questions and is_legacy_reading_questions(questions):
        return replace_markdown_section(content, "读后问题回答", read_after_question_body(DEFAULT_READING_QUESTIONS))
    return content


def replace_markdown_section(content: str, title: str, body: str) -> str:
    body = body.strip()
    section = f"## {title}\n\n{body}\n"
    pattern = rf"^##\s+{re.escape(title)}\s*$\n?.*?(?=^##\s+|\Z)"
    if re.search(pattern, content, flags=re.MULTILINE | re.DOTALL):
        return re.sub(pattern, lambda _match: section, content, count=1, flags=re.MULTILINE | re.DOTALL)
    if not content.endswith("\n"):
        content += "\n"
    return content.rstrip() + "\n\n" + section


def insert_markdown_section_before(content: str, before_title: str, title: str, body: str) -> str:
    body = body.strip()
    section = f"## {title}\n\n{body}\n\n"
    pattern = rf"^##\s+{re.escape(before_title)}\s*$"
    match = re.search(pattern, content, flags=re.MULTILINE)
    if not match:
        return replace_markdown_section(content, title, body)
    prefix = content[: match.start()].rstrip()
    suffix = content[match.start() :].lstrip("\n")
    return f"{prefix}\n\n{section}{suffix}"


def update_deep_reading_status_section(content: str, paper: dict[str, Any], model: str, status: str = "read") -> str:
    priority = paper.get("priority") or infer_priority(paper)
    body = (
        f"- 阅读状态：{status}\n"
        f"- 优先级：{priority}\n"
        "- PDF 精读：已完成\n"
        f"- 精读时间：{now_iso()}\n"
        f"- 模型：{model}\n"
    )
    return replace_markdown_section(content, "精读状态", body)


def select_pdf_text_tool(preferred: str = "auto") -> tuple[str, str] | None:
    base_url = os.environ.get("MINERU_API_BASE", "").strip().rstrip("/")
    if preferred in {"auto", "mineru-api", "mineru-precise", "mineru-agent"} and base_url:
        parser = os.environ.get("PDF_PARSER", "").strip().lower()
        if preferred == "mineru-precise" or base_url.endswith("/api/v4"):
            return ("mineru-api", "mineru-precise")
        if preferred == "mineru-agent" or preferred == "mineru-api" or not parser or parser in {"mineru", "mineru-api"}:
            return ("mineru-api", "mineru-agent")
    candidates = [
        ("mineru", "mineru"),
        ("magic-pdf", "mineru"),
        ("pdftotext", "pdftotext"),
        ("mutool", "mutool"),
    ]
    if preferred != "auto":
        candidates = [(cmd, kind) for cmd, kind in candidates if kind == preferred]
    for cmd, kind in candidates:
        if shutil.which(cmd):
            return (cmd, kind)
    return None


def pdf_cache_path(vault: Path, paper: dict[str, Any]) -> Path:
    key = stable_key(paper).replace(":", "-").replace("/", "-")
    slug = slugify(paper.get("title", ""), limit=64)
    return vault / "data" / "pdf_cache" / f"{key}-{slug}.pdf"


def mineru_cache_dir(vault: Path, paper: dict[str, Any]) -> Path:
    key = stable_key(paper).replace(":", "-").replace("/", "-")
    slug = slugify(paper.get("title", ""), limit=64)
    return vault / "data" / "mineru_cache" / f"{key}-{slug}"


def download_pdf(paper: dict[str, Any], target: Path, timeout: int) -> Path:
    pdf_url = paper.get("pdf") or ""
    if not pdf_url:
        raise ValueError("这篇论文没有 pdf 链接，无法精读。")
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(pdf_url, timeout=timeout)
    target.write_bytes(data)
    return target


def extract_pdf_text(pdf_path: Path, tool: tuple[str, str], timeout: int, output_dir: Path | None = None) -> str:
    command_name, tool_kind = tool
    if tool_kind == "mineru-precise":
        return extract_pdf_text_with_mineru_precise_api(pdf_path, timeout, output_dir=output_dir)
    if tool_kind == "mineru-agent":
        return extract_pdf_text_with_mineru_agent_api(pdf_path, timeout, output_dir=output_dir)
    if tool_kind == "mineru":
        if output_dir is None:
            raise RuntimeError("使用 MinerU 时缺少输出目录。")
        return extract_pdf_text_with_mineru(pdf_path, command_name, output_dir, timeout)
    if tool_kind == "pdftotext":
        command = [command_name, "-enc", "UTF-8", str(pdf_path), "-"]
    else:
        command = [command_name, "draw", "-F", "txt", "-o", "-", str(pdf_path)]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"PDF 文本抽取失败：{detail or '外部工具返回非零退出码'}")
    text = normalize_pdf_text(result.stdout)
    if len(text) < 1000:
        raise RuntimeError("PDF 文本抽取结果太短，可能是扫描版 PDF 或抽取工具不可用。")
    return text


def mineru_api_headers(content_type: str | None = "application/json") -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("MINERU_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def mineru_api_data(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("data"), dict):
        return response["data"]
    return response if isinstance(response, dict) else {}


def mineru_api_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 300) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=mineru_api_headers(), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MinerU API 调用失败：HTTP {exc.code} {detail}") from exc


def mineru_api_download_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers=mineru_api_headers(content_type=None))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MinerU Markdown 下载失败：HTTP {exc.code} {detail}") from exc


def mineru_upload_pdf(upload_url: str, pdf_path: Path, timeout: int) -> None:
    parsed = urllib.parse.urlparse(upload_url)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    body = pdf_path.read_bytes()
    connection = connection_cls(parsed.netloc, timeout=timeout)
    try:
        connection.putrequest("PUT", path)
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders()
        connection.send(body)
        response = connection.getresponse()
        detail = response.read().decode("utf-8", errors="replace")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"MinerU PDF 上传失败：HTTP {response.status} {detail}")
    finally:
        connection.close()


def mineru_parse_payload(pdf_path: Path) -> dict[str, Any]:
    return {
        "file_name": pdf_path.name,
        "language": os.environ.get("MINERU_LANGUAGE", "ch"),
        "enable_table": env_bool("MINERU_ENABLE_TABLE", True),
        "enable_formula": env_bool("MINERU_ENABLE_FORMULA", True),
        "is_ocr": env_bool("MINERU_IS_OCR", False),
    }


def mineru_precise_payload(pdf_path: Path) -> dict[str, Any]:
    return {
        "enable_formula": env_bool("MINERU_ENABLE_FORMULA", True),
        "enable_table": env_bool("MINERU_ENABLE_TABLE", True),
        "language": os.environ.get("MINERU_LANGUAGE", "ch"),
        "files": [
            {
                "name": pdf_path.name,
                "is_ocr": env_bool("MINERU_IS_OCR", False),
                "data_id": hashlib.sha1(str(pdf_path).encode("utf-8")).hexdigest()[:16],
            }
        ],
    }


def mineru_result_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["extract_result", "extract_results", "results", "files"]:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def mineru_status_done(status: str) -> bool:
    return status.lower() in {"done", "success", "succeeded", "completed", "complete"}


def mineru_status_failed(status: str) -> bool:
    return status.lower() in {"failed", "fail", "error", "canceled", "cancelled"}


def extract_mineru_zip(zip_bytes: bytes, output_dir: Path | None) -> None:
    if output_dir is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (output_dir / member.filename).resolve()
            root = output_dir.resolve()
            if root not in target.parents and target != root:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)


def mineru_zip_markdown(zip_bytes: bytes, output_dir: Path | None = None) -> str:
    extract_mineru_zip(zip_bytes, output_dir)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        preferred = [name for name in names if name.endswith("full.md")]
        markdown_names = preferred or [name for name in names if name.lower().endswith(".md")]
        if not markdown_names:
            raise RuntimeError("MinerU 精准解析结果 zip 中没有 Markdown 文件。")
        chunks = []
        for name in markdown_names[:5]:
            chunks.append(archive.read(name).decode("utf-8", errors="replace"))
        return normalize_pdf_text("\n\n".join(chunks))


def mineru_api_download_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers=mineru_api_headers(content_type=None))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MinerU 结果下载失败：HTTP {exc.code} {detail}") from exc


def extract_pdf_text_with_mineru_precise_api(pdf_path: Path, timeout: int, output_dir: Path | None = None) -> str:
    base_url = os.environ.get("MINERU_API_BASE", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("缺少 MINERU_API_BASE，无法使用 MinerU 精准解析。")
    if not os.environ.get("MINERU_API_TOKEN", "").strip():
        raise RuntimeError("缺少 MINERU_API_TOKEN，无法使用 MinerU 精准解析。")
    api_timeout = int(os.environ.get("MINERU_TIMEOUT", str(timeout)))
    poll_interval = float(os.environ.get("MINERU_POLL_INTERVAL", "3"))

    create_data = mineru_api_data(
        mineru_api_json(f"{base_url}/file-urls/batch", method="POST", payload=mineru_precise_payload(pdf_path), timeout=api_timeout)
    )
    batch_id = str(create_data.get("batch_id") or create_data.get("batchId") or "")
    file_urls = create_data.get("file_urls") or create_data.get("fileUrls") or create_data.get("urls") or []
    if not batch_id or not isinstance(file_urls, list) or not file_urls:
        raise RuntimeError("MinerU 精准解析创建任务失败：响应中缺少 batch_id 或 file_urls。")
    first_file = file_urls[0] if isinstance(file_urls[0], dict) else {"url": file_urls[0]}
    upload_url = str(first_file.get("url") or first_file.get("upload_url") or first_file.get("uploadUrl") or "")
    if not upload_url:
        raise RuntimeError("MinerU 精准解析创建任务失败：响应中缺少上传 URL。")

    mineru_upload_pdf(upload_url, pdf_path, timeout=api_timeout)
    deadline = time.monotonic() + api_timeout
    last_status = ""
    while time.monotonic() < deadline:
        poll_data = mineru_api_data(mineru_api_json(f"{base_url}/extract-results/batch/{urllib.parse.quote(batch_id)}", timeout=api_timeout))
        items = mineru_result_items(poll_data)
        if not items:
            last_status = str(poll_data.get("status") or poll_data.get("state") or "")
            time.sleep(poll_interval)
            continue
        item = items[0]
        last_status = str(item.get("state") or item.get("status") or poll_data.get("state") or poll_data.get("status") or "")
        full_zip_url = str(item.get("full_zip_url") or item.get("fullZipUrl") or item.get("zip_url") or item.get("zipUrl") or "")
        if full_zip_url and mineru_status_done(last_status):
            text = mineru_zip_markdown(mineru_api_download_bytes(full_zip_url, timeout=api_timeout), output_dir=output_dir)
            if len(text) >= 1000:
                return text
            raise RuntimeError("MinerU 精准解析 Markdown 太短，可能解析失败。")
        if mineru_status_failed(last_status):
            message = item.get("err_msg") or item.get("message") or item.get("error") or "未知错误"
            raise RuntimeError(f"MinerU 精准解析失败：{message}")
        time.sleep(poll_interval)
    raise RuntimeError(f"MinerU 精准解析超时，最后状态：{last_status or '未知'}")


def extract_pdf_text_with_mineru_agent_api(pdf_path: Path, timeout: int, output_dir: Path | None = None) -> str:
    base_url = os.environ.get("MINERU_API_BASE", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("缺少 MINERU_API_BASE，无法使用 MinerU API。")
    api_timeout = int(os.environ.get("MINERU_TIMEOUT", str(timeout)))
    poll_interval = float(os.environ.get("MINERU_POLL_INTERVAL", "3"))

    create_data = mineru_api_data(mineru_api_json(f"{base_url}/parse/file", method="POST", payload=mineru_parse_payload(pdf_path), timeout=api_timeout))
    task_id = str(create_data.get("task_id") or create_data.get("id") or "")
    upload_url = str(create_data.get("upload_url") or create_data.get("uploadUrl") or create_data.get("file_url") or create_data.get("fileUrl") or "")
    if not task_id or not upload_url:
        raise RuntimeError("MinerU API 创建解析任务失败：响应中缺少 task_id 或 upload_url。")

    mineru_upload_pdf(upload_url, pdf_path, timeout=api_timeout)
    deadline = time.monotonic() + api_timeout
    last_status = ""
    while time.monotonic() < deadline:
        poll_data = mineru_api_data(mineru_api_json(f"{base_url}/parse/{urllib.parse.quote(task_id)}", timeout=api_timeout))
        last_status = str(poll_data.get("status") or poll_data.get("state") or "").lower()
        markdown = poll_data.get("markdown") or poll_data.get("md")
        markdown_url = poll_data.get("markdown_url") or poll_data.get("markdownUrl") or poll_data.get("md_url")
        full_zip_url = str(poll_data.get("full_zip_url") or poll_data.get("fullZipUrl") or poll_data.get("zip_url") or poll_data.get("zipUrl") or "")
        if full_zip_url:
            text = mineru_zip_markdown(mineru_api_download_bytes(full_zip_url, timeout=api_timeout), output_dir=output_dir)
            if len(text) >= 1000:
                return text
            raise RuntimeError("MinerU API 下载的结果包 Markdown 太短，可能解析失败。")
        if markdown:
            text = normalize_pdf_text(str(markdown))
            if len(text) >= 1000:
                return text
            raise RuntimeError("MinerU API 返回的 Markdown 太短，可能解析失败。")
        if markdown_url:
            text = normalize_pdf_text(mineru_api_download_text(str(markdown_url), timeout=api_timeout))
            if len(text) >= 1000:
                return text
            raise RuntimeError("MinerU API 下载的 Markdown 太短，可能解析失败。")
        if last_status in {"failed", "fail", "error", "canceled", "cancelled"}:
            message = poll_data.get("message") or poll_data.get("error") or "未知错误"
            raise RuntimeError(f"MinerU API 解析失败：{message}")
        time.sleep(poll_interval)
    raise RuntimeError(f"MinerU API 解析超时，最后状态：{last_status or '未知'}")


def extract_pdf_text_with_mineru(pdf_path: Path, command_name: str, output_dir: Path, timeout: int) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [command_name, "-p", str(pdf_path), "-o", str(output_dir)]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"MinerU PDF 解析失败：{detail or '外部工具返回非零退出码'}")
    markdown_files = sorted(output_dir.rglob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not markdown_files:
        raise RuntimeError("MinerU 已运行，但没有找到输出的 Markdown 文件。")
    texts = []
    for path in markdown_files[:5]:
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    text = normalize_pdf_text("\n\n".join(texts))
    if len(text) < 1000:
        raise RuntimeError("MinerU 输出文本太短，可能解析失败或 PDF 内容不可抽取。")
    return text


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def resolve_figure_root(vault: Path, figure_dir: str) -> Path:
    path = Path(figure_dir)
    return path if path.is_absolute() else vault / path


def paper_figure_dir(vault: Path, paper: dict[str, Any], figure_dir: str) -> Path:
    year = paper.get("year") or "unknown"
    slug = slugify(paper.get("title", "paper"), limit=64)
    return resolve_figure_root(vault, figure_dir) / f"{year}-{slug}"


def markdown_image_path(note_path: Path, image_path: Path) -> str:
    return Path(os.path.relpath(image_path, start=note_path.parent)).as_posix()


def clean_caption(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(clean_caption(item) for item in value)
    elif isinstance(value, dict):
        parts = []
        for key in ["text", "content", "caption", "html"]:
            if key in value:
                parts.append(clean_caption(value.get(key)))
        value = " ".join(parts)
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def image_source_path_from_block(block: dict[str, Any]) -> str:
    for key in ["img_path", "image_path", "imagePath", "table_img_path", "tableImagePath", "path"]:
        value = block.get(key)
        if isinstance(value, str) and re.search(r"\.(?:png|jpe?g|webp|gif|bmp)$", value, flags=re.IGNORECASE):
            return value
    return ""


def figure_caption_from_block(block: dict[str, Any]) -> str:
    parts = []
    for key in ["image_caption", "caption", "figure_caption", "table_caption", "title", "text"]:
        value = block.get(key)
        if value:
            parts.append(clean_caption(value))
    return " ".join(part for part in parts if part).strip()


def page_idx_from_block(block: dict[str, Any]) -> int | None:
    for key in ["page_idx", "page_index", "page", "page_no", "pageNo"]:
        value = block.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def iter_mineru_figure_blocks(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            found.extend(iter_mineru_figure_blocks(item))
        return found
    if not isinstance(value, dict):
        return found
    block_type = str(value.get("type") or value.get("category") or value.get("block_type") or "").lower()
    source_path = image_source_path_from_block(value)
    if source_path and (not block_type or any(key in block_type for key in FIGURE_SOURCE_KEYS)):
        found.append(value)
    for child in value.values():
        if isinstance(child, (dict, list)):
            found.extend(iter_mineru_figure_blocks(child))
    return found


def mineru_json_files(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    preferred_patterns = [
        "*content_list*.json",
        "*middle*.json",
        "*model*.json",
        "layout.json",
    ]
    files: list[Path] = []
    for pattern in preferred_patterns:
        for path in sorted(output_dir.rglob(pattern)):
            if path not in files:
                files.append(path)
    extra = sorted(path for path in output_dir.rglob("*.json") if path not in files)
    return files + extra


def resolve_mineru_image_path(raw_path: str, json_path: Path, output_dir: Path) -> Path | None:
    path = Path(raw_path)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend([json_path.parent / path, output_dir / path])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    basename = path.name
    if basename:
        for candidate in output_dir.rglob(basename):
            if candidate.is_file():
                return candidate
    return None


def figure_id_from_caption(caption: str, fallback_index: int) -> str:
    match = re.search(r"(?:fig(?:ure)?\.?|图)\s*([0-9]+[a-zA-Z]?)", caption, flags=re.IGNORECASE)
    if match:
        number = match.group(1).lower()
        return f"fig-{number.zfill(2) if number.isdigit() else number}"
    return f"fig-{fallback_index:02d}"


def figure_filename(fig_id: str, caption: str, source_path: Path | None, kind: str) -> str:
    suffix = source_path.suffix.lower() if source_path and source_path.suffix else ".png"
    caption_slug = slugify(caption, limit=36) or slugify(kind, limit=16) or "figure"
    return f"{fig_id}-{caption_slug}{suffix}"


def score_key_figure(figure: dict[str, Any]) -> float:
    caption = clean_caption(figure.get("caption", ""))
    text = normalize_text(caption)
    score = 0.0
    kind = str(figure.get("kind") or "").lower()
    if kind in {"image", "figure"}:
        score += 8
    elif kind == "chart":
        score += 3
    elif kind == "table":
        score -= 10
    for term in KEY_FIGURE_TERMS:
        normalized_term = normalize_text(term)
        normalized_hit = bool(
            normalized_term
            and re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text)
        )
        if term.lower() in caption.lower() or normalized_hit:
            score += 12
    for term in LOW_VALUE_FIGURE_TERMS:
        normalized_term = normalize_text(term)
        normalized_hit = bool(
            normalized_term
            and re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text)
        )
        if term.lower() in caption.lower() or normalized_hit:
            score -= 8
    match = re.search(r"(?:fig(?:ure)?\.?|图)\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if match:
        number = int(match.group(1))
        if number <= 2:
            score += 14
        elif number <= 4:
            score += 6
    page_idx = figure.get("page_idx")
    if isinstance(page_idx, int) and page_idx <= 3:
        score += 5
    if not caption:
        score -= 6
    return score


def term_matches_caption(caption: str, terms: list[str]) -> bool:
    lowered = caption.lower()
    normalized_caption = normalize_text(caption)
    for term in terms:
        normalized_term = normalize_text(term)
        if term.lower() in lowered:
            return True
        if normalized_term and re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized_caption):
            return True
    return False


def is_overview_figure(figure: dict[str, Any]) -> bool:
    caption = clean_caption(figure.get("caption", ""))
    if not caption:
        return False
    kind = str(figure.get("kind") or "").lower()
    if kind == "table":
        return False
    if term_matches_caption(caption, LOW_VALUE_FIGURE_TERMS):
        return False
    return term_matches_caption(caption, OVERVIEW_FIGURE_TERMS)


def selected_figures(figures: list[dict[str, Any]], limit: int, focus: str = "overview") -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for figure in figures:
        if focus == "overview" and not is_overview_figure(figure):
            continue
        source = str(figure.get("source") or "")
        source_image_path = str(figure.get("source_image_path") or figure.get("target_path") or "")
        if source == "pymupdf":
            key = f"{source}::{source_image_path}::{figure.get('fig_id') or ''}"
        else:
            key = f"{source}::{source_image_path}" if source_image_path else str(figure.get("caption") or "")
        if not key:
            continue
        if key not in unique or float(figure.get("score", 0)) > float(unique[key].get("score", 0)):
            unique[str(key)] = figure
    ranked = sorted(unique.values(), key=lambda item: float(item.get("score", 0)), reverse=True)
    return ranked[: max(limit, 0)]


def extract_figures_with_mineru(
    mineru_output_dir: Path,
    paper: dict[str, Any],
    figure_dir: Path,
    note_path: Path,
    limit: int,
    focus: str = "overview",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    if not mineru_output_dir.exists():
        return []
    figures: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    figure_dir.mkdir(parents=True, exist_ok=True) if not dry_run else None
    for json_path in mineru_json_files(mineru_output_dir):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for block in iter_mineru_figure_blocks(data):
            raw_path = image_source_path_from_block(block)
            source_path = resolve_mineru_image_path(raw_path, json_path, mineru_output_dir)
            if source_path is None or str(source_path) in seen_sources:
                continue
            seen_sources.add(str(source_path))
            kind = str(block.get("type") or block.get("category") or "image").lower()
            caption = figure_caption_from_block(block)
            fig_id = figure_id_from_caption(caption, len(figures) + 1)
            target_path = figure_dir / figure_filename(fig_id, caption, source_path, kind)
            figure = {
                "fig_id": fig_id,
                "caption": caption or f"{fig_id}，MinerU 提取图片，图注待人工确认。",
                "source": "mineru",
                "kind": kind,
                "page_idx": page_idx_from_block(block),
                "bbox": block.get("bbox") if isinstance(block.get("bbox"), list) else None,
                "source_image_path": str(source_path),
                "target_path": str(target_path),
                "markdown_path": markdown_image_path(note_path, target_path),
            }
            figure["score"] = score_key_figure(figure)
            figures.append(figure)
    selected = selected_figures(figures, limit, focus=focus)
    if not dry_run:
        for figure in selected:
            source_path = Path(str(figure.get("source_image_path") or ""))
            target_path = Path(str(figure.get("target_path") or ""))
            if source_path.exists() and target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
    return selected


def extract_figures_from_mineru_loose_images(
    mineru_output_dir: Path,
    paper: dict[str, Any],
    figure_dir: Path,
    note_path: Path,
    limit: int,
    focus: str = "overview",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    if not mineru_output_dir.exists():
        return []
    image_paths = sorted(
        path
        for path in mineru_output_dir.rglob("*")
        if path.is_file() and re.search(r"\.(?:png|jpe?g|webp|gif|bmp)$", path.name, flags=re.IGNORECASE)
    )
    if not image_paths:
        return []
    figure_dir.mkdir(parents=True, exist_ok=True) if not dry_run else None
    figures = []
    for index, source_path in enumerate(image_paths[: max(limit * 3, limit)], 1):
        caption = source_path.stem.replace("_", " ").replace("-", " ")
        fig_id = figure_id_from_caption(caption, index)
        target_path = figure_dir / figure_filename(fig_id, caption, source_path, "image")
        figure = {
            "fig_id": fig_id,
            "caption": f"{caption}，MinerU 提取图片，图注待人工确认。",
            "source": "mineru",
            "kind": "image",
            "page_idx": None,
            "bbox": None,
            "source_image_path": str(source_path),
            "target_path": str(target_path),
            "markdown_path": markdown_image_path(note_path, target_path),
        }
        figure["score"] = score_key_figure(figure)
        figures.append(figure)
    selected = selected_figures(figures, limit, focus=focus)
    if not dry_run:
        for figure in selected:
            source_path = Path(str(figure.get("source_image_path") or ""))
            target_path = Path(str(figure.get("target_path") or ""))
            if source_path.exists() and target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
    return selected


def extract_figures_with_pymupdf_fallback(
    pdf_path: Path,
    paper: dict[str, Any],
    figure_dir: Path,
    note_path: Path,
    limit: int,
    focus: str = "overview",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if focus == "overview":
        return []
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception:
        return []
    figures: list[dict[str, Any]] = []
    figure_dir.mkdir(parents=True, exist_ok=True) if not dry_run else None
    with fitz.open(pdf_path) as doc:
        scored_pages: list[tuple[float, int, str]] = []
        for page_index in range(min(len(doc), 6)):
            page = doc[page_index]
            text = clean_caption(page.get_text("text"))
            score = 0.0
            lowered = text.lower()
            for term in KEY_FIGURE_TERMS:
                if term.lower() in lowered:
                    score += 6
            if re.search(r"(?:fig(?:ure)?\.?|图)\s*[12]", text, flags=re.IGNORECASE):
                score += 8
            score += max(0, 4 - page_index)
            scored_pages.append((score, page_index, text))
        for _score, page_index, page_text in sorted(scored_pages, reverse=True)[:limit]:
            target_path = figure_dir / f"page-{page_index + 1:02d}-fallback.png"
            if not dry_run:
                page = doc[page_index]
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(str(target_path))
            caption = f"PDF 第 {page_index + 1} 页截图，作为 MinerU 未提取到关键图时的兜底图片。"
            figure = {
                "fig_id": f"page-{page_index + 1:02d}",
                "caption": caption,
                "source": "pymupdf",
                "kind": "page",
                "page_idx": page_index,
                "bbox": None,
                "source_image_path": str(pdf_path),
                "target_path": str(target_path),
                "markdown_path": markdown_image_path(note_path, target_path),
                "score": 1.0,
            }
            figures.append(figure)
    return figures


def collect_deep_read_figures(
    pdf_path: Path,
    mineru_output_dir: Path,
    paper: dict[str, Any],
    note_path: Path,
    figure_dir: Path,
    source: str,
    limit: int,
    focus: str = "overview",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    if source in {"mineru-first", "mineru"}:
        figures = extract_figures_with_mineru(mineru_output_dir, paper, figure_dir, note_path, limit, focus=focus, dry_run=dry_run)
        if len(figures) < limit:
            loose = extract_figures_from_mineru_loose_images(
                mineru_output_dir,
                paper,
                figure_dir,
                note_path,
                limit - len(figures),
                focus=focus,
                dry_run=dry_run,
            )
            figures = selected_figures(figures + loose, limit, focus=focus)
    if source == "pymupdf" or (source == "mineru-first" and len(figures) < limit):
        fallback = extract_figures_with_pymupdf_fallback(
            pdf_path,
            paper,
            figure_dir,
            note_path,
            limit - len(figures) if source == "mineru-first" else limit,
            focus=focus,
            dry_run=dry_run,
        )
        figures = selected_figures(figures + fallback, limit, focus=focus)
    return figures


def cleanup_mineru_cached_images(mineru_output_dir: Path, figures: list[dict[str, Any]]) -> int:
    if not mineru_output_dir.exists():
        return 0
    keep = set()
    for figure in figures:
        source = str(figure.get("source") or "")
        if source != "mineru":
            continue
        source_path = str(figure.get("source_image_path") or "")
        if source_path:
            keep.add(Path(source_path).resolve())
    removed = 0
    for path in mineru_output_dir.rglob("*"):
        if not path.is_file():
            continue
        if not re.search(r"\.(?:png|jpe?g|webp|gif|bmp)$", path.name, flags=re.IGNORECASE):
            continue
        if path.resolve() in keep:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def figure_prompt_summary(figures: list[dict[str, Any]]) -> str:
    if not figures:
        return "无候选图片。"
    lines = []
    for index, figure in enumerate(figures[:8], 1):
        page = figure.get("page_idx")
        page_text = f"page={page}" if page is not None else "page=未知"
        lines.append(
            f"{index}. {figure.get('fig_id')} | source={figure.get('source')} | {page_text} | caption={clean_caption(figure.get('caption'))}"
        )
    return "\n".join(lines)


def auto_figure_block(figures: list[dict[str, Any]]) -> str:
    if not figures:
        return ""
    lines = ["<!-- auto-figures:start -->", "### 关键图", ""]
    for figure in figures:
        caption = clean_caption(figure.get("caption"))
        alt = caption[:80] or str(figure.get("fig_id") or "论文图片")
        markdown_path = str(figure.get("markdown_path") or "")
        if not markdown_path:
            continue
        lines.append(f"![{alt}]({markdown_path})")
        lines.append("")
        lines.append(f"图注：{caption}")
        lines.append("")
    lines.append("<!-- auto-figures:end -->")
    return "\n".join(lines).strip()


def strip_auto_figure_block(markdown: str) -> str:
    return re.sub(
        r"\n?<!-- auto-figures:start -->.*?<!-- auto-figures:end -->\n?",
        "\n",
        markdown,
        flags=re.DOTALL,
    ).strip()


def inject_figures_into_key_modules(content: str, figures: list[dict[str, Any]]) -> str:
    if not figures:
        return content
    body = markdown_section_body(content, "关键模块")
    if not body:
        return content
    body = strip_auto_figure_block(body)
    block = auto_figure_block(figures)
    if not block:
        return content
    return replace_markdown_section(content, "关键模块", f"{block}\n\n{body}")


def deep_read_prompt(
    paper: dict[str, Any],
    pdf_text: str,
    figures: list[dict[str, Any]] | None = None,
    reading_questions: list[str] | None = None,
) -> list[dict[str, str]]:
    clipped = pdf_text[:DEEP_READ_MAX_CHARS]
    questions = reading_questions or DEFAULT_READING_QUESTIONS
    question_text = "\n".join(f"- {question}" for question in questions)
    paper_meta = {
        "title": paper.get("title", ""),
        "authors": paper.get("authors") or [],
        "year": paper.get("year") or "",
        "venue": paper.get("venue") or "",
        "abstract": paper.get("abstract") or "",
        "tags": paper.get("tags") or [],
    }
    schema = {
        "核心问题": "一段中文，说明论文解决的具体问题。",
        "方法一句话": "一段中文，用普通话说明方法，不照抄标题。",
        "输入输出": "字符串数组，包含输入和输出。",
        "关键模块": "字符串数组，写成详细 Markdown 小节。每个数组元素对应一个模块，必须以 ### 模块 N：模块名 开头，并包含作用、输入输出、流程、公式、实现要点、比较价值。",
        "实验设置": "字符串数组，包含数据集、baseline、指标。",
        "主要结论": "字符串数组，说明最重要结论。",
        "局限/风险": "字符串数组，说明局限、不稳定点、未验证点。",
        "和我方向的关系": "字符串数组，包含可借鉴和不适合直接借鉴。",
        "可复用点": "字符串数组，包含代码、指标、实验设计、图表/写法。",
        "读后问题回答": "字符串数组，逐条回答卡片里的待读问题；每条先复述问题，再给出基于 PDF 的回答。",
        "精读可信度": "字符串数组，说明信息来源、是否仅基于 PDF 文本、模型不确定项。",
    }
    return [
        {
            "role": "system",
            "content": (
                "你是一个严谨的 3DGS 论文精读助手。只根据用户提供的论文元数据和 PDF 文本回答，"
                "不要编造 PDF 文本中没有的信息。不确定时明确写“待人工确认”。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请用中文精读这篇论文，输出严格 JSON 对象，不要使用 Markdown 代码块。"
                "除“核心问题”和“方法一句话”外，其余字段优先用字符串数组，数组元素里不要写未转义的双引号。\n"
                "重点要求：\n"
                "1. “关键模块”必须详细，不要只写模块名或一句话概括。\n"
                "2. 每个关键模块写成一个 Markdown 小节，格式为：### 模块 N：模块名。\n"
                "3. 每个模块至少包含：作用、输入、输出、具体流程、涉及公式、实现/训练细节、和其他方法比较时应该关注什么。\n"
                "4. 论文中出现的损失函数、约束、投影/反投影、权重、优化目标、评价指标公式，都要尽量写入对应模块。\n"
                "5. 所有数学符号都必须使用 Markdown 公式语法：短符号用行内公式 `$...$`，例如 `$\\theta_y$`、`$I_y^M$`、`$\\lambda_i$`；不要裸写 theta_y、lambda_i，也不要把符号替换成中文占位。\n"
                "6. 完整公式、损失函数、求和、优化目标，必须单独成块：上一行说明公式含义，下一行写 `$$`，中间写 LaTeX，下一行再写 `$$`。\n"
                "7. 不要把长公式塞进中文句子里；不要用逗号替代 LaTeX 乘法或空格，乘法/并列权重优先用 `\\,` 或 `\\cdot`。\n"
                "8. 如果论文没有给出公式，写“公式：论文未给出明确公式，待人工确认”。\n"
                "9. 不确定公式含义时，不要硬猜；保留原符号并说明待人工确认。\n"
                "10. 如果提供了候选图片清单，可以在关键模块文字中自然提到相关 Fig 编号；"
                "但只能引用清单中实际存在的图片编号，不要编造不存在的图或图注。\n"
                "11. “读后问题回答”必须逐条回答下面的待读问题；每条答案都要基于 PDF 文本，"
                "如果 PDF 没有足够证据，明确写“待人工确认”。\n"
                f"JSON 字段必须正好覆盖这些键：{json.dumps(schema, ensure_ascii=False)}\n\n"
                f"论文元数据：\n{json.dumps(paper_meta, ensure_ascii=False, indent=2)}\n\n"
                f"待读问题（精读时优先围绕这些问题找答案）：\n{question_text}\n\n"
                f"候选图片清单：\n{figure_prompt_summary(figures or [])}\n\n"
                f"PDF 文本节选（最多 {DEEP_READ_MAX_CHARS} 字符）：\n{clipped}"
            ),
        },
    ]


def call_deepseek(messages: list[dict[str, str]], api_key: str, model: str, base_url: str, timeout: int) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek 调用失败：HTTP {exc.code} {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"DeepSeek 调用失败：{exc}") from exc
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("DeepSeek 没有返回可解析内容。")
    try:
        return parse_deep_read_json(content)
    except RuntimeError:
        repaired = repair_deepseek_json(content, api_key=api_key, model=model, base_url=base_url, timeout=timeout)
        return parse_deep_read_json(repaired)


def repair_deepseek_json(content: str, api_key: str, model: str, base_url: str, timeout: int) -> str:
    required = [title for title, _body in READING_DETAIL_SECTIONS] + ["精读可信度"]
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你只负责把输入修复成合法 JSON 对象。不要新增解释，不要使用 Markdown 代码块。",
            },
            {
                "role": "user",
                "content": (
                    "请把下面内容修复成严格合法 JSON。"
                    f"必须保留这些键：{json.dumps(required, ensure_ascii=False)}。"
                    "所有值都用字符串或字符串数组。关键模块字段必须保留原来的 Markdown 小节和公式，不要压缩成摘要。\n\n"
                    f"{content[:20000]}"
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek JSON 修复失败：HTTP {exc.code} {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"DeepSeek JSON 修复失败：{exc}") from exc
    repaired = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not repaired:
        raise RuntimeError("DeepSeek JSON 修复没有返回内容。")
    return repaired


def parse_deep_read_json(content: str) -> dict[str, str]:
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DeepSeek 返回内容不是合法 JSON：{exc}") from exc
    required = [title for title, _body in READING_DETAIL_SECTIONS] + ["精读可信度"]
    result: dict[str, str] = {}
    for key in required:
        value = data.get(key, "")
        if isinstance(value, list):
            if key == "关键模块":
                value = "\n\n".join(str(item).strip() for item in value if str(item).strip())
            else:
                value = "\n".join(f"- {item}" for item in value)
        elif not isinstance(value, str):
            value = str(value) if value else ""
        result[key] = value.strip() or "- 待人工确认：模型未返回这一项。"
    return result


def inline_math_label(expr: str) -> str:
    expr = expr.strip()
    expr = expr.replace(r"\mathcal{L}{\mathrm{adv}}", r"\mathcal{L}_{\mathrm{adv}}")
    return f"${normalize_latex_expr(expr)}$"


def is_full_formula(expr: str) -> bool:
    expr = expr.strip()
    formula_markers = [
        "=",
        r"\sum",
        r"\prod",
        r"\arg",
        r"\min",
        r"\max",
        r"\nabla",
        r"\Pi",
        r"\|",
        r"\leq",
        r"\geq",
    ]
    return any(marker in expr for marker in formula_markers)


def normalize_latex_expr(expr: str) -> str:
    expr = expr.strip()
    expr = re.sub(r"(?<!\\)\b(mathcal|mathrm|operatorname)\s*\{", r"\\\1{", expr)
    expr = expr.replace(r"\mathcal{L}{\mathrm{adv}}", r"\mathcal{L}_{\mathrm{adv}}")

    def compact_command(match: re.Match[str]) -> str:
        command = match.group(1)
        body = re.sub(r"\s+", "", match.group(2))
        return f"\\{command}{{{body}}}"

    expr = re.sub(r"\\(mathcal|mathrm|operatorname)\s*\{\s*([^{}]+?)\s*\}", compact_command, expr)
    expr = re.sub(r"_\s*\\mathrm\{([^{}]+)\}", lambda match: f"_{{\\mathrm{{{match.group(1)}}}}}", expr)
    expr = re.sub(r"\^\s*\\mathrm\{([^{}]+)\}", lambda match: f"^{{\\mathrm{{{match.group(1)}}}}}", expr)
    expr = re.sub(r"([_^])\s*\{\s*", r"\1{", expr)
    expr = re.sub(r"\{\s+", "{", expr)
    expr = re.sub(r"\s+\}", "}", expr)
    expr = re.sub(r"\s+,", ",", expr)
    expr = re.sub(r"\s+\.", ".", expr)
    expr = re.sub(r"\s+\)", ")", expr)
    expr = re.sub(r"\(\s+", "(", expr)
    expr = re.sub(r"\\\s+", r"\\", expr)
    expr = re.sub(r"\s{2,}", " ", expr)
    return expr


def cleanup_inline_math(markdown: str) -> str:
    output_lines = []
    in_block = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "$$":
            in_block = not in_block
            output_lines.append(line)
            continue
        if in_block:
            output_lines.append(normalize_latex_expr(line))
            continue
        line = re.sub(r"\\\((.+?)\\\)", lambda match: inline_math_label(match.group(1)), line)
        if "$" not in line:
            output_lines.append(line)
            continue
        matches = re.findall(r"\$([^$\n]+)\$", line)
        if not matches:
            output_lines.append(line)
            continue
        clean_line = re.sub(r"\$([^$\n]+)\$", lambda match: inline_math_label(match.group(1)), line)
        output_lines.append(clean_line)
        for expr in matches:
            expr = normalize_latex_expr(expr)
            if not is_full_formula(expr):
                continue
            output_lines.extend(["", "$$", expr, "$$"])
    return "\n".join(output_lines).strip()


def normalize_math_syntax(markdown: str) -> str:
    output_lines = []
    in_block = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "$$":
            in_block = not in_block
            output_lines.append(line)
            continue
        if in_block:
            output_lines.append(normalize_latex_expr(line))
            continue
        protected_math: list[str] = []

        def protect_inline_math(match: re.Match[str]) -> str:
            protected_math.append(match.group(0))
            return f"\u0000MATH{len(protected_math) - 1}\u0000"

        line = re.sub(r"\$[^$\n]+\$", protect_inline_math, line)
        line = re.sub(
            r"\(\s*([^()\n]*(?:\\|mathcal|mathrm|operatorname|_\{|[\^_]|K_p|K_l|\\eta|\\alpha|\\beta)[^()\n]*)\s*\)",
            lambda match: f"${normalize_latex_expr(match.group(1))}$",
            line,
        )
        line = re.sub(r"\\\((.+?)\\\)", lambda match: f"${normalize_latex_expr(match.group(1))}$", line)
        for index, math in enumerate(protected_math):
            line = line.replace(f"\u0000MATH{index}\u0000", math)
        line = re.sub(r"\$([^$\n]+)\$", lambda match: f"${normalize_latex_expr(match.group(1))}$", line)
        output_lines.append(line)
    return "\n".join(output_lines).strip()


def looks_like_formula_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped in {"$$", "---"}:
        return False
    if "://" in stripped or re.match(r"^[A-Za-z_][\w-]*:\s", stripped):
        return False
    if len(stripped.split()) > 20 and "=" not in stripped:
        return False
    if re.match(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s+)", stripped):
        return False
    if re.match(r"^[*_`]", stripped):
        return False
    if re.search(r"[\u4e00-\u9fff]", stripped):
        return False
    if not re.search(r"(\\[A-Za-z]+|[_^]\{|[=<>]|\\\||\|_|_\w|\^\w)", stripped):
        return False
    return bool(
        re.search(
            r"(=|\\sum|\\prod|\\arg|\\min|\\max|\\nabla|\\Pi|\\leq|\\geq|\\mathcal|\\mathrm|\\operatorname|\\|)",
            stripped,
        )
    )


def strip_inline_math(line: str) -> str:
    line = re.sub(r"\$\$.*?\$\$", "", line)
    return re.sub(r"\$[^$\n]*\$", "", line)


def repair_math_fences(markdown: str) -> str:
    raw_lines = markdown.splitlines()
    deduped: list[str] = []
    for index, line in enumerate(raw_lines):
        stripped = line.strip()
        if stripped != "$$":
            deduped.append(line)
            continue
        prev = next((item.strip() for item in reversed(deduped) if item.strip()), "")
        next_text = ""
        for later in raw_lines[index + 1 :]:
            if later.strip():
                next_text = later.strip()
                break
        if prev == "$$" and not looks_like_formula_line(next_text):
            continue
        deduped.append(line)

    output_lines: list[str] = []
    in_block = False
    for line in deduped:
        stripped = line.strip()
        if stripped == "$$":
            in_block = not in_block
            output_lines.append(line)
            continue
        if in_block:
            if re.match(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s+|\*\*)", stripped):
                if output_lines and output_lines[-1].strip() == "$$":
                    output_lines.pop()
                    in_block = False
                else:
                    output_lines.append("$$")
                    in_block = False
            else:
                output_lines.append(normalize_latex_expr(line))
                continue
        if looks_like_formula_line(line):
            if output_lines and output_lines[-1].strip():
                output_lines.append("")
            output_lines.extend(["$$", normalize_latex_expr(line), "$$"])
        else:
            output_lines.append(line)
    if in_block:
        output_lines.append("$$")
    return "\n".join(output_lines).strip()


def repair_markdown_format(markdown: str) -> str:
    markdown = repair_math_fences(markdown)
    markdown = normalize_math_syntax(markdown)
    markdown = repair_math_fences(markdown)
    markdown = re.sub(r"(^|\n)(\s*[-*+]\s+)\*\s+\*([^*\n]+?)\s*\*\*[:：]", r"\1\2**\3**：", markdown)
    markdown = re.sub(r"\\mathcal\{([A-Za-z])\}\{\\mathrm\{([^{}]+)\}\}", r"\\mathcal{\1}_{\\mathrm{\2}}", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def audit_markdown_format(markdown: str) -> list[str]:
    findings: list[str] = []
    lines = markdown.splitlines()
    if sum(1 for line in lines if line.strip() == "$$") % 2:
        findings.append("unbalanced $$ math fences")

    in_block = False
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "$$":
            in_block = not in_block
            continue
        if in_block:
            if re.match(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s+|\*\*)", stripped):
                findings.append(f"line {line_no}: prose/list text is inside a math block")
            continue

        visible = strip_inline_math(line)
        if re.search(r"\\(?:mathcal|mathrm|operatorname|alpha|beta|eta|lambda|nabla|Pi|ell|boldsymbol)", visible):
            findings.append(f"line {line_no}: raw LaTeX appears outside math delimiters")
        if looks_like_formula_line(line):
            findings.append(f"line {line_no}: standalone formula is missing $$ block delimiters")
        if re.search(r"(^|\s)\*\s+\*", line):
            findings.append(f"line {line_no}: broken bold marker")
        if re.search(r"\\mathcal\{[A-Za-z]\}\{\\mathrm\{", line):
            findings.append(f"line {line_no}: malformed subscript LaTeX")
        if line.replace("$$", "").count("$") % 2:
            findings.append(f"line {line_no}: unbalanced inline $ delimiters")
    return findings


def prepare_deep_read_markdown(markdown: str, context: str) -> str:
    cleaned = repair_markdown_format(markdown)
    findings = audit_markdown_format(cleaned)
    if findings:
        detail = "; ".join(findings[:8])
        if len(findings) > 8:
            detail += f"; ... and {len(findings) - 8} more"
        raise ValueError(f"Markdown format audit failed in {context}: {detail}")
    return cleaned


def blockify_inline_math(markdown: str) -> str:
    output_lines = []
    in_block = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "$$":
            in_block = not in_block
            output_lines.append(line)
            continue
        if in_block:
            output_lines.append(normalize_latex_expr(line))
            continue
        line = re.sub(r"\\\((.+?)\\\)", lambda match: f"${normalize_latex_expr(match.group(1))}$", line)
        matches = re.findall(r"\$([^$\n]+)\$", line)
        if not matches:
            output_lines.append(line)
            continue
        clean = re.sub(r"\$([^$\n]+)\$", "", line)
        clean = re.sub(r"\s+([，。；：、])", r"\1", clean)
        clean = re.sub(r"([：，、]){2,}", r"\1", clean)
        clean = clean.strip()
        if clean:
            output_lines.append(clean)
        output_lines.append("")
        output_lines.append("相关符号/公式：")
        for expr in matches:
            expr = normalize_latex_expr(expr)
            output_lines.extend(["", "$$", expr, "$$"])
    return "\n".join(output_lines).strip()


def apply_deep_read_result(
    content: str,
    paper: dict[str, Any],
    result: dict[str, str],
    model: str,
    figures: list[dict[str, Any]] | None = None,
) -> str:
    read_paper = {**paper, "reading_status": "read"}
    content = ensure_reading_template(content, paper)
    content = set_frontmatter_field(content, "reading_status", "read")
    content = update_deep_reading_status_section(content, read_paper, model, status="read")
    for title, _body in READING_DETAIL_SECTIONS:
        content = replace_markdown_section(content, title, prepare_deep_read_markdown(result[title], title))
    content = replace_markdown_section(
        content,
        "精读可信度",
        prepare_deep_read_markdown(result["精读可信度"], "精读可信度"),
    )
    if figures:
        content = inject_figures_into_key_modules(content, figures)
    return content.rstrip() + "\n"


def render_deep_read_preview(
    paper: dict[str, Any],
    result: dict[str, str],
    model: str,
    figures: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        f"# 精读预览：{paper.get('title', 'Untitled')}",
        "",
        "## 精读状态",
        "",
        f"- 阅读状态：{paper.get('reading_status') or paper.get('status') or 'candidate'}",
        f"- 优先级：{paper.get('priority') or infer_priority(paper)}",
        "- PDF 精读：已完成",
        f"- 精读时间：{now_iso()}",
        f"- 模型：{model}",
        "",
    ]
    for title, _body in READING_DETAIL_SECTIONS:
        body = prepare_deep_read_markdown(result[title], title)
        if title == "关键模块" and figures:
            body = strip_auto_figure_block(body)
            body = f"{auto_figure_block(figures)}\n\n{body}"
        lines.extend([f"## {title}", "", body, ""])
    lines.extend(["## 精读可信度", "", prepare_deep_read_markdown(result["精读可信度"], "精读可信度"), ""])
    return "\n".join(lines)


def hydrate_paper_from_note(vault: Path | None, paper: dict[str, Any]) -> dict[str, Any]:
    if vault is None:
        return dict(paper)
    hydrated = dict(paper)
    note = hydrated.get("note_path", "")
    if not note:
        return hydrated
    path = vault / note
    if not path.exists():
        return hydrated
    content = path.read_text(encoding="utf-8")
    reading_status = extract_frontmatter_value(content, "reading_status")
    priority = extract_frontmatter_value(content, "priority")
    if reading_status:
        hydrated["reading_status"] = reading_status
    if priority:
        hydrated["priority"] = priority
    return hydrated


def make_paper(
    *,
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
    venue: str = "",
    source: str,
    url: str = "",
    pdf: str = "",
    abstract: str = "",
    ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    tags = infer_tags(title, abstract)
    created = now_iso()
    paper = {
        "title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
        "authors": authors or [],
        "year": year,
        "venue": venue,
        "source": source,
        "sources": [source],
        "ids": ids or {},
        "url": url,
        "pdf": pdf,
        "abstract": html.unescape(re.sub(r"\s+", " ", abstract)).strip(),
        "tags": tags,
        "status": "candidate",
        "comment": short_comment(title, abstract, tags),
        "created": created,
        "updated": created,
    }
    paper["key"] = stable_key(paper)
    return paper


def merge_paper(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old)
    for field in ["title", "venue", "url", "pdf", "abstract", "source", "year"]:
        if not merged.get(field) and new.get(field):
            merged[field] = new[field]
    merged["authors"] = merged.get("authors") or new.get("authors") or []
    merged["ids"] = {**(new.get("ids") or {}), **(merged.get("ids") or {})}
    merged["tags"] = sorted(set((merged.get("tags") or []) + (new.get("tags") or [])))
    merged["sources"] = sorted(set((merged.get("sources") or []) + (new.get("sources") or [new.get("source")])))
    urls = [value for value in (merged.get("urls") or []) if value]
    for value in [merged.get("url"), new.get("url")]:
        if value and value not in urls:
            urls.append(value)
    if urls:
        merged["urls"] = urls
    pdfs = [value for value in (merged.get("pdfs") or []) if value]
    for value in [merged.get("pdf"), new.get("pdf")]:
        if value and value not in pdfs:
            pdfs.append(value)
    if pdfs:
        merged["pdfs"] = pdfs
    if new.get("citationCount") is not None:
        merged["citationCount"] = new["citationCount"]
    if new.get("semantic_scholar_url"):
        merged["semantic_scholar_url"] = new["semantic_scholar_url"]
    merged["comment"] = merged.get("comment") or new.get("comment") or short_comment(
        merged.get("title", ""), merged.get("abstract", ""), merged.get("tags", [])
    )
    merged["updated"] = now_iso()
    merged["key"] = stable_key(merged)
    return merged


def search_arxiv(query_name: str, limit: int, warnings: list[str], timeout: int) -> list[dict[str, Any]]:
    terms = SEARCH_PROFILES.get(query_name, [query_name])
    query = "cat:cs.CV AND (" + " OR ".join(f'all:"{term}"' for term in terms) + ")"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        raw = http_get_text("https://export.arxiv.org/api/query", params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"arXiv 检索失败：{exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(raw)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        if not contains_related_text(title, abstract):
            continue
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        entry_id = entry.findtext("atom:id", default="", namespaces=ns) or ""
        arxiv_id = entry_id.rstrip("/").split("/")[-1]
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        pdf = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf = link.attrib.get("href", "")
        papers.append(
            make_paper(
                title=title,
                authors=authors,
                year=year,
                venue="arXiv",
                source="arXiv",
                url=entry_id,
                pdf=pdf,
                abstract=abstract,
                ids={"arxiv": arxiv_id} if arxiv_id else {},
            )
        )
    return papers


def extract_cvf_entries(page: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'<dt class="ptitle">\s*<br>\s*<a href="(?P<href>[^"]+)">(?P<title>.*?)</a>\s*</dt>\s*'
        r'<dd>\s*(?P<authors>.*?)\s*</dd>',
        re.DOTALL | re.IGNORECASE,
    )
    entries = []
    for match in pattern.finditer(page):
        title = re.sub(r"<.*?>", "", match.group("title"))
        authors = re.sub(r"<.*?>", "", match.group("authors"))
        entries.append(
            {
                "title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
                "authors": html.unescape(re.sub(r"\s+", " ", authors)).strip(),
                "href": html.unescape(match.group("href")).strip(),
            }
        )
    return entries


def fetch_cvf_abstract(url: str, timeout: int) -> str:
    try:
        page = http_get_text(url, timeout=timeout)
    except Exception:
        return ""
    match = re.search(r'<div id="abstract"[^>]*>(?P<abstract>.*?)</div>', page, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    text = re.sub(r"<.*?>", " ", match.group("abstract"))
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def search_cvf(limit: int, warnings: list[str], timeout: int, venues: list[str] | None = None) -> list[dict[str, Any]]:
    venues = venues or DEFAULT_CVF_VENUES
    papers: list[dict[str, Any]] = []
    for venue in venues:
        if len(papers) >= limit:
            break
        url = f"https://openaccess.thecvf.com/{venue}?day=all"
        try:
            page = http_get_text(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"CVF {venue} 检索失败：{exc}")
            continue
        entries = extract_cvf_entries(page)
        year_match = re.search(r"(20\d{2})", venue)
        year = int(year_match.group(1)) if year_match else None
        for entry in entries:
            if len(papers) >= limit:
                break
            title = entry["title"]
            if not contains_related_text(title):
                continue
            detail_url = urllib.parse.urljoin("https://openaccess.thecvf.com/", entry["href"])
            abstract = fetch_cvf_abstract(detail_url, timeout=timeout)
            authors = [name.strip() for name in entry["authors"].split(",") if name.strip()]
            pdf = detail_url.replace("/html/", "/papers/").replace(".html", ".pdf")
            papers.append(
                make_paper(
                    title=title,
                    authors=authors,
                    year=year,
                    venue=venue,
                    source="CVF",
                    url=detail_url,
                    pdf=pdf,
                    abstract=abstract,
                )
            )
    return papers


def openreview_content_value(content: dict[str, Any], key: str) -> Any:
    value = content.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def search_openreview(limit: int, warnings: list[str], timeout: int, venues: list[str] | None = None) -> list[dict[str, Any]]:
    venues = venues or DEFAULT_OPENREVIEW_VENUES
    papers: list[dict[str, Any]] = []
    for venue in venues:
        if len(papers) >= limit:
            break
        params = {"content.venueid": venue, "limit": min(1000, max(limit * 20, 100))}
        try:
            payload = http_get_json("https://api2.openreview.net/notes", params=params, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"OpenReview {venue} 检索失败：{exc}")
            continue
        for note in payload.get("notes", []):
            if len(papers) >= limit:
                break
            content = note.get("content") or {}
            title = str(openreview_content_value(content, "title") or "").strip()
            abstract = str(openreview_content_value(content, "abstract") or "").strip()
            if not title or not contains_related_text(title, abstract):
                continue
            authors_value = openreview_content_value(content, "authors") or []
            if isinstance(authors_value, str):
                authors = [authors_value]
            else:
                authors = [str(author) for author in authors_value]
            year_match = re.search(r"(20\d{2})", venue)
            year = int(year_match.group(1)) if year_match else None
            note_id = note.get("id", "")
            papers.append(
                make_paper(
                    title=title,
                    authors=authors,
                    year=year,
                    venue=venue,
                    source="OpenReview",
                    url=f"https://openreview.net/forum?id={note_id}" if note_id else "",
                    pdf=f"https://openreview.net/pdf?id={note_id}" if note_id else "",
                    abstract=abstract,
                    ids={"openreview": note_id} if note_id else {},
                )
            )
    return papers


def semantic_scholar_enrich(paper: dict[str, Any], warnings: list[str], timeout: int) -> dict[str, Any]:
    title = paper.get("title", "")
    if not title:
        return paper
    params = {
        "query": title,
        "limit": 1,
        "fields": "paperId,title,abstract,venue,year,citationCount,externalIds,url,authors",
    }
    try:
        payload = http_get_json("https://api.semanticscholar.org/graph/v1/paper/search", params=params, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            warnings.append("Semantic Scholar 触发限流，已跳过后续补全。")
        else:
            warnings.append(f"Semantic Scholar 补全失败：HTTP {exc.code}")
        return paper
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Semantic Scholar 补全失败：{exc}")
        return paper

    results = payload.get("data") or []
    if not results:
        return paper
    result = results[0]
    result_title = result.get("title") or ""
    if normalize_title(result_title) != normalize_title(title):
        return paper
    ids = dict(paper.get("ids") or {})
    external_ids = result.get("externalIds") or {}
    if result.get("paperId"):
        ids["semantic_scholar"] = result["paperId"]
    if external_ids.get("DOI"):
        ids["doi"] = external_ids["DOI"]
    if external_ids.get("ArXiv") and not ids.get("arxiv"):
        ids["arxiv"] = external_ids["ArXiv"]
    enriched = dict(paper)
    enriched["ids"] = ids
    enriched["venue"] = enriched.get("venue") or result.get("venue") or ""
    enriched["year"] = enriched.get("year") or result.get("year")
    enriched["citationCount"] = result.get("citationCount")
    enriched["semantic_scholar_url"] = result.get("url", "")
    if not enriched.get("abstract") and result.get("abstract"):
        enriched["abstract"] = result["abstract"]
    if not enriched.get("authors"):
        enriched["authors"] = [author.get("name", "") for author in result.get("authors", []) if author.get("name")]
    enriched["tags"] = infer_tags(enriched.get("title", ""), enriched.get("abstract", ""))
    enriched["comment"] = short_comment(enriched.get("title", ""), enriched.get("abstract", ""), enriched["tags"])
    enriched["key"] = stable_key(enriched)
    return enriched


def sample_papers() -> list[dict[str, Any]]:
    return [
        make_paper(
            title="GaussianEditor: Swift and Controllable 3D Editing with Gaussian Splatting",
            authors=["Sample Author"],
            year=2024,
            venue="Sample",
            source="Sample",
            url="https://example.com/gaussianeditor",
            pdf="https://example.com/gaussianeditor.pdf",
            abstract=(
                "A sample record for testing a local Obsidian workflow about controllable "
                "3D Gaussian Splatting editing and scene manipulation."
            ),
            ids={"sample": "gaussianeditor"},
        )
    ]


def collect_candidates(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []
    if args.sample:
        candidates = sample_papers()
    else:
        sources = set(args.sources)
        per_source_limit = max(1, args.limit)
        timeout = max(3, args.timeout)
        if "arxiv" in sources:
            candidates.extend(search_arxiv(args.query, per_source_limit, warnings, timeout=timeout))
            time.sleep(args.delay)
        if "cvf" in sources:
            candidates.extend(search_cvf(per_source_limit, warnings, timeout=timeout))
            time.sleep(args.delay)
        if "openreview" in sources:
            candidates.extend(search_openreview(per_source_limit, warnings, timeout=timeout))

    if args.enrich and not args.sample:
        enriched = []
        semantic_limited = False
        for paper in candidates:
            if semantic_limited:
                enriched.append(paper)
                continue
            before = len(warnings)
            enriched_paper = semantic_scholar_enrich(paper, warnings, timeout=timeout)
            if len(warnings) > before and "限流" in warnings[-1]:
                semantic_limited = True
            enriched.append(enriched_paper)
            time.sleep(args.delay)
        candidates = enriched

    deduped: dict[str, dict[str, Any]] = {}
    for paper in candidates:
        key = stable_key(paper)
        paper["key"] = key
        deduped[key] = merge_paper(deduped[key], paper) if key in deduped else paper

    data = {
        "query": args.query,
        "generated": now_iso(),
        "count": len(deduped),
        "warnings": warnings,
        "papers": sorted(deduped.values(), key=lambda item: (item.get("year") or 0, item.get("title", "")), reverse=True),
    }
    save_json(vault / "data" / "candidates.json", data)
    print(f"已保存候选论文 {len(deduped)} 篇：{vault / 'data' / 'candidates.json'}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def yaml_quote(value: Any) -> str:
    if value is None:
        return '""'
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def yaml_list(values: list[Any]) -> str:
    return "[" + ", ".join(yaml_quote(value) for value in values) + "]"


def yaml_ids(ids: dict[str, str]) -> str:
    if not ids:
        return "{}"
    lines = []
    for key in sorted(ids):
        lines.append(f"  {key}: {yaml_quote(ids[key])}")
    return "\n" + "\n".join(lines)


def paper_filename(paper: dict[str, Any]) -> str:
    year = paper.get("year") or "unknown"
    return f"{year}-{slugify(paper.get('title', 'paper'))}.md"


def find_existing_key_by_title(papers_by_key: dict[str, dict[str, Any]], title: str) -> str | None:
    normalized = normalize_title(title)
    if not normalized:
        return None
    for key, paper in papers_by_key.items():
        if normalize_title(paper.get("title", "")) == normalized:
            return key
    for key, paper in papers_by_key.items():
        if is_similar_title(paper.get("title", ""), title):
            return key
    return None


def paper_quality_score(paper: dict[str, Any]) -> tuple[int, int, int, int]:
    ids = paper.get("ids") or {}
    stable_ids = sum(1 for key in ["doi", "arxiv", "semantic_scholar"] if ids.get(key))
    source_score = len(paper.get("sources") or [paper.get("source")])
    abstract_score = 1 if paper.get("abstract") else 0
    url_score = 1 if paper.get("url") else 0
    return (stable_ids, source_score, abstract_score, url_score)


def render_paper_card(paper: dict[str, Any]) -> str:
    title = paper.get("title", "Untitled")
    authors = paper.get("authors") or []
    tags = paper.get("tags") or ["paper", "3dgs"]
    abstract = paper.get("abstract") or "暂无摘要。"
    related_topics = ", ".join(f"#{tag}" for tag in tags if tag != "paper")
    ids = yaml_ids(paper.get("ids") or {})
    citation = paper.get("citationCount")
    citation_line = f"- Semantic Scholar 引用数：{citation}\n" if citation is not None else ""
    ss_url = paper.get("semantic_scholar_url")
    ss_line = f"- Semantic Scholar：{ss_url}\n" if ss_url else ""
    priority = paper.get("priority") or infer_priority(paper)
    reading_status = paper.get("reading_status") or paper.get("status") or "candidate"
    content = (
        "---\n"
        f"title: {yaml_quote(title)}\n"
        f"authors: {yaml_list(authors)}\n"
        f"year: {paper.get('year') or ''}\n"
        f"venue: {yaml_quote(paper.get('venue', ''))}\n"
        f"source: {yaml_quote(paper.get('source', ''))}\n"
        f"ids: {ids}\n"
        f"url: {yaml_quote(paper.get('url', ''))}\n"
        f"pdf: {yaml_quote(paper.get('pdf', ''))}\n"
        f"tags: {yaml_list(tags)}\n"
        f"status: {yaml_quote(paper.get('status', 'candidate'))}\n"
        f"reading_status: {yaml_quote(reading_status)}\n"
        f"priority: {yaml_quote(priority)}\n"
        f"created: {yaml_quote(paper.get('created', now_iso()))}\n"
        f"updated: {yaml_quote(now_iso())}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## 一句话短评\n\n"
        f"{paper.get('comment') or short_comment(title, abstract, tags)}\n\n"
        "## 为什么和 3DGS 编辑相关\n\n"
        f"- 相关主题：{related_topics or '#3dgs'}\n"
        f"- 来源：{', '.join(paper.get('sources') or [paper.get('source', '')])}\n"
        f"- 链接：{paper.get('url') or '暂无'}\n"
        f"- PDF：{paper.get('pdf') or '暂无'}\n"
        f"{ss_line}"
        f"{citation_line}\n"
        "## 摘要\n\n"
        f"{abstract}\n\n"
        "## 可能关联主题\n\n"
        + "\n".join(f"- [[Indexes/3DGS|3DGS]] #{tag}" for tag in tags if tag != "paper")
        + "\n\n"
        "## 待读问题\n\n"
        f"{question_list_body(DEFAULT_READING_QUESTIONS)}"
    )
    return ensure_reading_template(content, {**paper, "priority": priority, "reading_status": reading_status})


def update_index(vault: Path, library: dict[str, Any]) -> None:
    papers = sorted(relevant_papers(library, vault), key=lambda item: (item.get("year") or 0, item.get("title", "")), reverse=True)
    lines = [
        "# 3D Scene Editing 论文索引",
        "",
        f"更新时间：{now_iso()}",
        "",
        "## 主题",
        "",
        "- `3dgs`",
        "- `3d-scene-editing`",
        "- `scene-editing`",
        "- `text-guided`",
        "- `local-editing`",
        "- `semantic`",
        "- `appearance`",
        "- `geometry`",
        "",
        "## 整理入口",
        "",
        "- [[Indexes/3DGS-comparison|3DGS 论文横向对比表]]",
        "- 阶段性整理报告见 `Reports/` 目录。",
        "",
        "## 论文列表",
        "",
    ]
    if not papers:
        lines.append("暂无论文。")
    else:
        lines.append("| 年份 | 论文 | Venue | 优先级 | 阅读状态 | 标签 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for paper in papers:
            note_path = paper.get("note_path", "")
            link = f"[[{note_path[:-3]}|{paper.get('title', 'Untitled')}]]" if note_path.endswith(".md") else paper.get("title", "")
            tags = " ".join(
                f"#{tag}" for tag in infer_tags(paper.get("title", ""), paper.get("abstract", ""))
            )
            lines.append(
                f"| {paper.get('year') or ''} | {link} | {paper.get('venue') or ''} | "
                f"{paper.get('priority') or infer_priority(paper)} | "
                f"{paper.get('reading_status') or paper.get('status') or 'candidate'} | {tags} |"
            )
    (vault / "Indexes").mkdir(parents=True, exist_ok=True)
    (vault / "Indexes" / "3DGS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ingest(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    candidates_path = vault / "data" / "candidates.json"
    candidates_data = load_json(candidates_path, {"papers": []})
    candidates = candidates_data.get("papers", [])
    if not candidates:
        print(f"没有可入库候选论文，请先运行 search：{candidates_path}", file=sys.stderr)
        return 1

    library_path = vault / "data" / "library.json"
    library = load_json(library_path, {"version": 1, "papers": {}})
    papers_by_key = library.setdefault("papers", {})
    new_count = 0
    updated_count = 0
    skipped_count = 0

    for paper in candidates:
        if not contains_related_text(paper.get("title", ""), paper.get("abstract", "")):
            skipped_count += 1
            continue
        key = stable_key(paper)
        existing_key = key if key in papers_by_key else find_existing_key_by_title(papers_by_key, paper.get("title", ""))
        existing = papers_by_key.get(existing_key) if existing_key else None
        merged = merge_paper(existing, paper) if existing else paper
        if existing:
            updated_count += 1
        else:
            new_count += 1
            merged["created"] = merged.get("created") or now_iso()
        filename = existing.get("note_path") if existing else None
        if not filename:
            filename = f"Papers/{paper_filename(merged)}"
        merged["note_path"] = filename
        merged["reading_status"] = merged.get("reading_status") or merged.get("status") or "candidate"
        merged["priority"] = merged.get("priority") or infer_priority(merged)
        merged["updated"] = now_iso()
        note_path = vault / filename
        if note_path.exists():
            current_content = note_path.read_text(encoding="utf-8")
            note_path.write_text(ensure_reading_template(current_content, merged), encoding="utf-8")
        else:
            note_path.write_text(render_paper_card(merged), encoding="utf-8")
        merged_key = stable_key(merged)
        if existing_key and existing_key != merged_key:
            papers_by_key.pop(existing_key, None)
        papers_by_key[merged_key] = merged

    library["updated"] = now_iso()
    merged_count, deleted_files = dedupe_library(library, vault, delete_files=True)
    save_json(library_path, library)
    update_index(vault, library)
    print(
        f"入库完成：新增 {new_count} 篇，更新 {updated_count} 篇，"
        f"跳过不相关 {skipped_count} 篇，合并重复 {merged_count} 篇，删除重复卡片 {deleted_files} 个。"
    )
    print(f"索引已更新：{vault / 'Indexes' / '3DGS.md'}")
    return 0


def render_report(library: dict[str, Any], limit: int) -> str:
    papers = sorted(
        [paper for paper in library.get("papers", {}).values() if contains_related_text(paper.get("title", ""), paper.get("abstract", ""))],
        key=lambda item: (item.get("updated", ""), item.get("year") or 0),
        reverse=True,
    )[:limit]
    lines = [
        f"# 3DGS 阅读候选报告 - {today()}",
        "",
        f"生成时间：{now_iso()}",
        "",
        "## 本期重点",
        "",
    ]
    if not papers:
        lines.append("暂无论文。")
    else:
        for index, paper in enumerate(papers, start=1):
            note = paper.get("note_path", "")
            link = f"[[{note[:-3]}|{paper.get('title', 'Untitled')}]]" if note.endswith(".md") else paper.get("title", "")
            tags = infer_tags(paper.get("title", ""), paper.get("abstract", ""))
            lines.extend(
                [
                    f"### {index}. {link}",
                    "",
                    f"- 年份/会议：{paper.get('year') or ''} / {paper.get('venue') or ''}",
                    f"- 标签：{' '.join('#' + tag for tag in tags)}",
                    f"- 短评：{short_comment(paper.get('title', ''), paper.get('abstract', ''), tags)}",
                    f"- 链接：{paper.get('url') or '暂无'}",
                    "",
                ]
            )
    lines.extend(
        [
            "## 下一步阅读建议",
            "",
            "- 优先阅读和 3D Scene Editing、object-level editing、text-guided editing 直接相关的论文。",
            "- 对每篇重点论文补充：方法入口、可复现实验、和自己课题的连接点。",
            "- 后续可以增加 PDF 精读模块，把方法、实验和局限自动补到卡片里。",
        ]
    )
    return "\n".join(lines) + "\n"


def make_report(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    library = load_json(vault / "data" / "library.json", {"papers": {}})
    report = render_report(library, args.limit)
    report_path = vault / "Reports" / f"{today()}-3DGS-reading-report.md"
    report_path.write_text(report, encoding="utf-8")
    update_index(vault, library)
    print(f"报告已生成：{report_path}")
    return 0


def relevant_papers(library: dict[str, Any], vault: Path | None = None) -> list[dict[str, Any]]:
    papers = [hydrate_paper_from_note(vault, paper) for paper in library.get("papers", {}).values()]
    return sorted(
        [paper for paper in papers if contains_related_text(paper.get("title", ""), paper.get("abstract", ""))],
        key=lambda item: (item.get("priority") or infer_priority(item), item.get("year") or 0, item.get("title", "")),
    )


def paper_link(paper: dict[str, Any]) -> str:
    note = paper.get("note_path", "")
    if note.endswith(".md"):
        return f"[[{note[:-3]}|{paper.get('title', 'Untitled')}]]"
    return paper.get("title", "Untitled")


def prepare_reading(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    library_path = vault / "data" / "library.json"
    library = load_json(library_path, {"version": 1, "papers": {}})
    changed = 0
    skipped = 0
    selected = relevant_papers(library, vault)
    if args.priority:
        selected = [paper for paper in selected if (paper.get("priority") or infer_priority(paper)) == args.priority]
    if args.limit:
        selected = selected[: args.limit]
    papers_by_key = library.setdefault("papers", {})

    for paper in selected:
        note = paper.get("note_path", "")
        if not note:
            skipped += 1
            continue
        path = vault / note
        if not path.exists():
            skipped += 1
            continue
        paper["reading_status"] = paper.get("reading_status") or args.status or paper.get("status") or "candidate"
        paper["priority"] = paper.get("priority") or infer_priority(paper)
        stored = papers_by_key.get(stable_key(paper))
        if stored is None:
            existing_key = find_existing_key_by_title(papers_by_key, paper.get("title", ""))
            stored = papers_by_key.get(existing_key) if existing_key else None
        if stored is not None:
            stored["reading_status"] = paper["reading_status"]
            stored["priority"] = paper["priority"]
        old = path.read_text(encoding="utf-8")
        new = ensure_reading_template(old, paper)
        if new != old:
            path.write_text(new, encoding="utf-8")
            changed += 1

    library["updated"] = now_iso()
    save_json(library_path, library)
    print(f"精读模板检查完成：更新 {changed} 篇，跳过 {skipped} 篇。")
    return 0


def deep_read(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    load_env_file(vault)
    library = load_json(vault / "data" / "library.json", {"papers": {}})
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("缺少 DEEPSEEK_API_KEY 环境变量，无法调用 DeepSeek V4 Pro。", file=sys.stderr)
        return 1

    text_tool = select_pdf_text_tool(args.pdf_tool)
    if not text_tool:
        print("未找到 PDF 文本抽取工具。请先安装本地 MinerU、pdftotext 或 mutool，然后重新运行 deep-read。", file=sys.stderr)
        return 1

    selected = relevant_papers(library, vault)
    if args.priority:
        selected = [paper for paper in selected if (paper.get("priority") or infer_priority(paper)) == args.priority]
    if args.status:
        selected = [paper for paper in selected if (paper.get("reading_status") or paper.get("status") or "candidate") == args.status]
    if args.paper:
        keyword = normalize_text(args.paper)
        selected = [
            paper
            for paper in selected
            if keyword in normalize_text(paper.get("title", "")) or keyword in normalize_text(paper.get("note_path", ""))
        ]
    if not args.force:
        selected = [paper for paper in selected if (paper.get("reading_status") or paper.get("status") or "candidate") != "read"]
    if args.limit:
        selected = selected[: args.limit]
    if not selected:
        print("没有找到符合条件的待精读论文。")
        return 0

    changed = 0
    skipped = 0
    for paper in selected:
        note = paper.get("note_path", "")
        if not note:
            print(f"跳过：{paper.get('title', 'Untitled')} 没有 note_path。", file=sys.stderr)
            skipped += 1
            continue
        note_path = vault / note
        if not note_path.exists():
            print(f"跳过：卡片不存在 {note_path}", file=sys.stderr)
            skipped += 1
            continue
        note_content = ""
        try:
            note_content = note_path.read_text(encoding="utf-8")
            reading_questions = extract_reading_questions(note_content)
            pdf_path = download_pdf(paper, pdf_cache_path(vault, paper), timeout=args.timeout)
            mineru_dir = mineru_cache_dir(vault, paper)
            pdf_text = extract_pdf_text(pdf_path, text_tool, timeout=args.timeout, output_dir=mineru_dir)
            figures: list[dict[str, Any]] = []
            if args.with_figures:
                try:
                    figures = collect_deep_read_figures(
                        pdf_path=pdf_path,
                        mineru_output_dir=mineru_dir,
                        paper=paper,
                        note_path=note_path,
                        figure_dir=paper_figure_dir(vault, paper, args.figure_dir),
                        source=args.figure_source,
                        limit=args.figure_limit,
                        focus=args.figure_focus,
                        dry_run=args.dry_run,
                    )
                    if not args.dry_run:
                        removed_cache_images = cleanup_mineru_cached_images(mineru_dir, figures)
                        if removed_cache_images:
                            print(f"已清理 MinerU 缓存图片：{removed_cache_images} 张")
                except Exception as figure_exc:  # noqa: BLE001
                    print(f"图片提取失败，将只写入文字精读：{paper.get('title', 'Untitled')}：{figure_exc}", file=sys.stderr)
            result = call_deepseek(
                deep_read_prompt(paper, pdf_text, figures=figures, reading_questions=reading_questions),
                api_key=api_key,
                model=args.model,
                base_url=args.base_url,
                timeout=args.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"精读失败：{paper.get('title', 'Untitled')}：{exc}", file=sys.stderr)
            skipped += 1
            continue

        try:
            if args.dry_run:
                if args.with_figures:
                    print("候选插图：")
                    if figures:
                        for figure in figures:
                            print(
                                f"- {figure.get('fig_id')} [{figure.get('source')}] "
                                f"{figure.get('markdown_path')}：{clean_caption(figure.get('caption'))}"
                            )
                    else:
                        print("- 未找到可插入图片。")
                    print("")
                print(render_deep_read_preview(paper, result, args.model, figures=figures))
                continue

            old = note_content
            new = apply_deep_read_result(old, paper, result, args.model, figures=figures)
        except Exception as exc:  # noqa: BLE001
            print(f"精读格式审核/写回失败：{paper.get('title', 'Untitled')}：{exc}", file=sys.stderr)
            skipped += 1
            continue

        if new != old:
            note_path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"已写回精读卡片：{note_path}")
            if args.with_figures:
                print(f"已插入/更新图片：{len(figures)} 张")
        else:
            print(f"卡片无需更新：{note_path}")

    if args.dry_run:
        print(f"dry-run 完成：预览 {len(selected) - skipped} 篇，跳过 {skipped} 篇，未写入卡片。")
    else:
        print(f"AI 精读完成：写回 {changed} 篇，跳过 {skipped} 篇。")
    return 0 if skipped == 0 else 1


def render_comparison_index(library: dict[str, Any], vault: Path | None = None) -> str:
    papers = relevant_papers(library, vault)
    lines = [
        "# 3DGS 论文横向对比表",
        "",
        f"更新时间：{now_iso()}",
        "",
        "这张表用于把候选论文从“列表”变成“可比较材料”。任务类型和方法线索来自标题、摘要和标签，精读后可以在单篇卡片里继续修正。",
        "",
        "| 优先级 | 阅读状态 | 年份/会议 | 论文 | 任务类型 | 方法线索 | 代码 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not papers:
        lines.append("|  |  |  | 暂无论文 |  |  |  |")
    for paper in papers:
        priority = paper.get("priority") or infer_priority(paper)
        reading_status = paper.get("reading_status") or paper.get("status") or "candidate"
        task = "、".join(infer_task_labels(paper))
        methods = "、".join(infer_method_clues(paper))
        code_hint = extract_code_hint(paper)
        lines.append(
            f"| {priority} | {reading_status} | {paper.get('year') or ''} / {paper.get('venue') or ''} | "
            f"{paper_link(paper)} | {task} | {methods} | {code_hint} |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "",
            "- 先读优先级 A 的论文，把单篇卡片里的“核心问题、方法一句话、实验设置、局限/风险、可复用点”补全。",
            "- 每读完一篇，把 `reading_status` 从 `candidate` 改成 `read`。",
            "- 如果某篇和方向关系不大，把 `reading_status` 改成 `skipped`，后续报告会更清楚。",
        ]
    )
    return "\n".join(lines) + "\n"


def make_comparison(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    library = load_json(vault / "data" / "library.json", {"papers": {}})
    update_index(vault, library)
    path = vault / "Indexes" / "3DGS-comparison.md"
    path.write_text(render_comparison_index(library, vault), encoding="utf-8")
    print(f"横向对比表已生成：{path}")
    return 0


def route_summary(papers: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    routes: dict[str, list[dict[str, Any]]] = {
        "文本/语言驱动编辑": [],
        "局部/物体级编辑": [],
        "语义分割/场景解耦": [],
        "外观/风格编辑": [],
        "几何/形变编辑": [],
        "安全/水印/防篡改": [],
        "通用 3DGS 编辑": [],
    }
    for paper in papers:
        labels = infer_task_labels(paper)
        for label in labels:
            if label in routes:
                routes[label].append(paper)
    return [(label, items) for label, items in routes.items() if items]


def route_gap_hint(route: str) -> str:
    hints = {
        "文本/语言驱动编辑": "重点看语言指令如何落到 3D Gaussian，尤其是目标区域泄漏、跨视角一致性和语义对应关系。",
        "局部/物体级编辑": "重点看物体删除、插入、inpainting 后的 3D 一致性，以及是否有真实 ground truth。",
        "语义分割/场景解耦": "重点看开放词汇、部分视角、遮挡和实例级 grounding 的稳定性。",
        "外观/风格编辑": "重点看风格强度、纹理一致性、几何保持和是否支持局部控制。",
        "几何/形变编辑": "重点看形变控制、结构保持、mesh/geometry 约束和可编辑范围。",
        "安全/水印/防篡改": "重点看所有权追踪、防编辑和对正常编辑流程的影响。",
        "通用 3DGS 编辑": "重点看是否是真正可控编辑，而不只是重建或渲染质量提升。",
    }
    return hints.get(route, "待精读后补充。")


def render_organization_report(library: dict[str, Any], limit: int, vault: Path | None = None) -> str:
    papers = relevant_papers(library, vault)
    top = papers[:limit]
    lines = [
        f"# 3DGS 论文整理阶段报告 - {today()}",
        "",
        f"生成时间：{now_iso()}",
        "",
        "## 当前判断",
        "",
        "当前库里已经不缺候选论文，下一步重点是把论文按任务、方法和实验拆开，形成可比较的精读材料。下面的判断基于标题、摘要和标签，精读 PDF 后需要继续修正。",
        "",
        "## 主流路线",
        "",
    ]
    if not papers:
        lines.append("暂无论文。")
    else:
        for route, items in route_summary(papers):
            examples = "；".join(paper_link(paper) for paper in items[:3])
            lines.extend(
                [
                    f"### {route}",
                    "",
                    f"- 候选数量：{len(items)}",
                    f"- 代表论文：{examples}",
                    f"- 阅读重点：{route_gap_hint(route)}",
                    "",
                ]
            )

    lines.extend(
        [
            "## 本轮优先精读",
            "",
        ]
    )
    if not top:
        lines.append("暂无优先论文。")
    for index, paper in enumerate(top, start=1):
        lines.extend(
            [
                f"### {index}. {paper_link(paper)}",
                "",
                f"- 优先级：{paper.get('priority') or infer_priority(paper)}",
                f"- 阅读状态：{paper.get('reading_status') or paper.get('status') or 'candidate'}",
                f"- 任务类型：{'、'.join(infer_task_labels(paper))}",
                f"- 方法线索：{'、'.join(infer_method_clues(paper))}",
                f"- 下一步：打开 PDF，补全单篇卡片里的核心问题、方法、实验、局限和可复用点。",
                "",
            ]
        )
    lines.extend(
        [
            "## 后续动作",
            "",
            "- 先完成 5-10 篇优先级 A 论文精读。",
            "- 更新 `Indexes/3DGS-comparison.md`，把抽象标签改成精读后的真实判断。",
            "- 当精读卡片足够多时，再用 PaperSpine 做 SOTA/gap map、citation bank 或正式综述。",
        ]
    )
    return "\n".join(lines) + "\n"


def make_organization_report(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    library = load_json(vault / "data" / "library.json", {"papers": {}})
    report = render_organization_report(library, args.limit, vault)
    path = vault / "Reports" / f"{today()}-3DGS-organization-report.md"
    path.write_text(report, encoding="utf-8")
    print(f"阶段性整理报告已生成：{path}")
    return 0


def organize(args: argparse.Namespace) -> int:
    code = prepare_reading(argparse.Namespace(vault=args.vault, limit=args.limit, priority=args.priority, status=args.status))
    if code:
        return code
    code = make_comparison(argparse.Namespace(vault=args.vault))
    if code:
        return code
    return make_organization_report(argparse.Namespace(vault=args.vault, limit=args.report_limit))


def resolve_inside_vault(vault: Path, relative_path: str) -> Path:
    target = (vault / relative_path).resolve()
    if not str(target).lower().startswith(str(vault.resolve()).lower()):
        raise ValueError(f"拒绝处理 vault 外部路径：{target}")
    return target


def dedupe_library(library: dict[str, Any], vault: Path, delete_files: bool = False) -> tuple[int, int]:
    papers_by_key = library.setdefault("papers", {})
    items = list(papers_by_key.items())
    removed_keys: set[str] = set()
    deleted_files = 0

    for i, (left_key, left_paper) in enumerate(items):
        if left_key in removed_keys:
            continue
        for right_key, right_paper in items[i + 1 :]:
            if right_key in removed_keys:
                continue
            if not is_similar_title(left_paper.get("title", ""), right_paper.get("title", "")):
                continue
            if paper_quality_score(right_paper) > paper_quality_score(left_paper):
                keep_key, keep_paper = right_key, right_paper
                drop_key, drop_paper = left_key, left_paper
            else:
                keep_key, keep_paper = left_key, left_paper
                drop_key, drop_paper = right_key, right_paper
            merged = merge_paper(keep_paper, drop_paper)
            merged["note_path"] = keep_paper.get("note_path") or drop_paper.get("note_path")
            papers_by_key[keep_key] = merged
            if drop_key in papers_by_key:
                papers_by_key.pop(drop_key)
            removed_keys.add(drop_key)
            drop_note = drop_paper.get("note_path", "")
            keep_note = merged.get("note_path", "")
            if delete_files and drop_note and drop_note != keep_note:
                target = resolve_inside_vault(vault, drop_note)
                if target.exists() and target.is_file():
                    target.unlink()
                    deleted_files += 1
            left_key, left_paper = keep_key, merged

    return len(removed_keys), deleted_files


def prune_library(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    library_path = vault / "data" / "library.json"
    library = load_json(library_path, {"version": 1, "papers": {}})
    papers_by_key = library.setdefault("papers", {})
    keep: dict[str, dict[str, Any]] = {}
    removed = []
    deleted_files = 0

    for key, paper in papers_by_key.items():
        if contains_related_text(paper.get("title", ""), paper.get("abstract", "")):
            keep[key] = paper
            continue
        removed.append(paper)
        note_path = paper.get("note_path", "")
        if args.delete_files and note_path:
            target = resolve_inside_vault(vault, note_path)
            if target.exists() and target.is_file():
                target.unlink()
                deleted_files += 1

    library["papers"] = keep
    merged_count, merged_deleted = dedupe_library(library, vault, delete_files=args.delete_files)
    deleted_files += merged_deleted
    library["updated"] = now_iso()
    save_json(library_path, library)
    update_index(vault, library)
    make_report(argparse.Namespace(vault=str(vault), limit=args.report_limit))
    print(f"清理完成：保留 {len(library['papers'])} 篇，移除不相关 {len(removed)} 篇，合并重复 {merged_count} 篇，删除卡片 {deleted_files} 个。")
    if removed and not args.delete_files:
        print("提示：本次只移除库记录，没有删除卡片文件；如需删除文件请加 --delete-files。")
    return 0


def latest_report(vault: Path) -> Path | None:
    reports = sorted((vault / "Reports").glob("*3DGS-reading-report.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def lark_message_from_report(report: str, max_chars: int = 3500) -> str:
    lines = []
    for line in report.splitlines():
        if line.startswith("# ") or line.startswith("### ") or line.startswith("- 年份/会议") or line.startswith("- 标签") or line.startswith("- 短评") or line.startswith("- 链接"):
            lines.append(line)
    message = "\n".join(lines)
    if len(message) > max_chars:
        message = message[: max_chars - 20] + "\n...(已截断)"
    return message


def lark_cli_command(args: list[str]) -> list[str]:
    executable = shutil.which("lark-cli") or "lark-cli"
    if os.name == "nt" and executable.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable] + args
    return [executable] + args


def run_lark_command(args: list[str], dry_run: bool) -> int:
    cmd = lark_cli_command(args)
    if dry_run and "--dry-run" not in cmd:
        cmd.append("--dry-run")
    print("执行命令：", " ".join(cmd))
    result = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def push_lark(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_dirs(vault)
    config_path = vault / "config.local.json"
    config = load_json(config_path, {})
    report_path = Path(args.report).resolve() if args.report else latest_report(vault)
    if not report_path or not report_path.exists():
        print("没有找到报告，先运行：python Scripts/kb.py report", file=sys.stderr)
        return 1
    report = report_path.read_text(encoding="utf-8")
    message = lark_message_from_report(report)
    dry_run = args.dry_run or not args.send

    print(f"飞书消息预览（dry_run={dry_run}）：\n")
    print(message)
    print("")

    lark = config.get("lark") or {}
    identity = lark.get("identity") or "user"
    chat_id = lark.get("chat_id") or ""
    doc_token = lark.get("doc_token") or ""
    create_doc = bool(lark.get("create_doc"))
    parent_token = lark.get("parent_token") or ""
    parent_position = lark.get("parent_position") or "my_library"

    if not config_path.exists():
        print(f"未找到 {config_path}，已只输出预览。可复制 config.local.example.json 后填写飞书目标。")
        return 0 if dry_run else 1

    exit_code = 0
    if doc_token:
        exit_code |= run_lark_command(
            [
                "docs",
                "+update",
                "--api-version",
                "v2",
                "--as",
                identity,
                "--doc",
                doc_token,
                "--command",
                "append",
                "--doc-format",
                "markdown",
                "--content",
                f"@{report_path}",
            ],
            dry_run=dry_run,
        )
    elif create_doc:
        cmd = [
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--as",
            identity,
            "--doc-format",
            "markdown",
            "--content",
            f"@{report_path}",
        ]
        if parent_token:
            cmd.extend(["--parent-token", parent_token])
        if parent_position:
            cmd.extend(["--parent-position", parent_position])
        exit_code |= run_lark_command(cmd, dry_run=dry_run)
    else:
        print("未配置 doc_token 或 create_doc=true，跳过飞书文档输出。")

    if chat_id:
        exit_code |= run_lark_command(
            [
                "im",
                "+messages-send",
                "--as",
                identity,
                "--chat-id",
                chat_id,
                "--markdown",
                message,
            ],
            dry_run=dry_run,
        )
    else:
        print("未配置 chat_id，跳过飞书群消息。")
    return exit_code


def run_all(args: argparse.Namespace) -> int:
    search_args = argparse.Namespace(**vars(args))
    code = collect_candidates(search_args)
    if code != 0:
        return code
    code = ingest(argparse.Namespace(vault=args.vault))
    if code != 0:
        return code
    code = make_report(argparse.Namespace(vault=args.vault, limit=args.report_limit))
    if code != 0:
        return code
    return push_lark(
        argparse.Namespace(
            vault=args.vault,
            report=None,
            dry_run=True,
            send=False,
        )
    )


def refresh_local(args: argparse.Namespace) -> int:
    search_args = argparse.Namespace(**vars(args))
    code = collect_candidates(search_args)
    if code != 0:
        return code
    code = ingest(argparse.Namespace(vault=args.vault))
    if code != 0:
        return code
    return make_report(argparse.Namespace(vault=args.vault, limit=args.report_limit))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="3DGS Obsidian knowledge-base workflow")
    parser.add_argument("--vault", default=str(ROOT), help="Obsidian vault path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search paper sources and save candidates")
    search.add_argument("--query", default="3d-scene-editing", help="query profile or raw query")
    search.add_argument("--limit", type=int, default=20, help="max papers per source")
    search.add_argument("--sources", nargs="+", default=["arxiv", "cvf", "openreview"], choices=["arxiv", "cvf", "openreview"])
    search.add_argument("--delay", type=float, default=1.0, help="delay between API calls")
    search.add_argument("--timeout", type=int, default=15, help="network timeout per request")
    search.add_argument("--sample", action="store_true", help="use local sample data for offline tests")
    search.add_argument("--enrich", dest="enrich", action="store_true", default=True, help="enrich with Semantic Scholar")
    search.add_argument("--no-enrich", dest="enrich", action="store_false", help="skip Semantic Scholar enrichment")
    search.set_defaults(func=collect_candidates)

    ingest_cmd = subparsers.add_parser("ingest", help="write paper cards and update index")
    ingest_cmd.set_defaults(func=ingest)

    report = subparsers.add_parser("report", help="generate reading report")
    report.add_argument("--limit", type=int, default=15, help="max papers in report")
    report.set_defaults(func=make_report)

    prepare = subparsers.add_parser("prepare-reading", help="add deep-reading fields to existing paper cards")
    prepare.add_argument("--limit", type=int, default=0, help="max cards to update; 0 means all")
    prepare.add_argument("--priority", choices=PRIORITY_VALUES, default="", help="only update papers with this priority")
    prepare.add_argument("--status", choices=READING_STATUS_VALUES, default="candidate", help="default reading status for new fields")
    prepare.set_defaults(func=prepare_reading)

    deep = subparsers.add_parser("deep-read", help="use DeepSeek V4 Pro to deep-read PDFs and update paper cards")
    deep.add_argument("--limit", type=int, default=1, help="max papers to deep-read; 0 means all matched papers")
    deep.add_argument("--priority", choices=PRIORITY_VALUES, default="", help="only deep-read papers with this priority")
    deep.add_argument("--status", choices=READING_STATUS_VALUES, default="", help="only deep-read papers with this reading status")
    deep.add_argument("--paper", default="", help="title or note-path keyword")
    deep.add_argument("--force", action="store_true", help="allow processing papers already marked read")
    deep.add_argument("--dry-run", action="store_true", help="preview generated content without writing paper cards")
    deep.add_argument("--model", default=DEFAULT_DEEPSEEK_MODEL, help="DeepSeek model name")
    deep.add_argument("--base-url", default=DEFAULT_DEEPSEEK_BASE_URL, help="DeepSeek OpenAI-compatible base URL")
    deep.add_argument("--pdf-tool", choices=PDF_TEXT_TOOL_VALUES, default="auto", help="PDF text extraction tool")
    deep.add_argument("--timeout", type=int, default=120, help="timeout for PDF download, extraction, and API calls")
    deep.add_argument("--with-figures", action="store_true", help="extract and insert key paper figures into deep-reading notes")
    deep.add_argument("--figure-limit", type=int, default=3, help="max figures to insert per paper")
    deep.add_argument("--figure-dir", default="Assets/Figures", help="vault-relative directory for long-lived figure assets")
    deep.add_argument("--figure-source", choices=FIGURE_SOURCE_VALUES, default="mineru-first", help="figure extraction source strategy")
    deep.add_argument(
        "--figure-focus",
        choices=FIGURE_FOCUS_VALUES,
        default="overview",
        help="overview keeps only architecture/framework/pipeline figures; broad also allows module/result figures",
    )
    deep.set_defaults(func=deep_read)

    comparison = subparsers.add_parser("comparison", help="generate cross-paper comparison index")
    comparison.set_defaults(func=make_comparison)

    organize_report = subparsers.add_parser("organize-report", help="generate stage organization report")
    organize_report.add_argument("--limit", type=int, default=10, help="max papers in priority-reading section")
    organize_report.set_defaults(func=make_organization_report)

    organize_cmd = subparsers.add_parser("organize", help="prepare cards, comparison index, and organization report")
    organize_cmd.add_argument("--limit", type=int, default=0, help="max cards to prepare; 0 means all")
    organize_cmd.add_argument("--priority", choices=PRIORITY_VALUES, default="", help="only prepare papers with this priority")
    organize_cmd.add_argument("--status", choices=READING_STATUS_VALUES, default="candidate", help="default reading status for new fields")
    organize_cmd.add_argument("--report-limit", type=int, default=10, help="max papers in organization report")
    organize_cmd.set_defaults(func=organize)

    prune = subparsers.add_parser("prune", help="remove papers that no longer match the topic filter")
    prune.add_argument("--delete-files", action="store_true", help="delete non-matching paper card files too")
    prune.add_argument("--report-limit", type=int, default=15, help="max papers in regenerated report")
    prune.set_defaults(func=prune_library)

    push = subparsers.add_parser("push-lark", help="preview or push report to Lark")
    push.add_argument("--report", default="", help="report path; default uses latest report")
    push.add_argument("--dry-run", action="store_true", default=False, help="preview lark-cli requests")
    push.add_argument("--send", action="store_true", help="actually send/update via lark-cli")
    push.set_defaults(func=push_lark)

    run = subparsers.add_parser("run", help="search, ingest, report, then lark dry-run")
    run.add_argument("--query", default="3d-scene-editing", help="query profile or raw query")
    run.add_argument("--limit", type=int, default=20, help="max papers per source")
    run.add_argument("--sources", nargs="+", default=["arxiv", "cvf", "openreview"], choices=["arxiv", "cvf", "openreview"])
    run.add_argument("--delay", type=float, default=1.0, help="delay between API calls")
    run.add_argument("--timeout", type=int, default=15, help="network timeout per request")
    run.add_argument("--sample", action="store_true", help="use local sample data for offline tests")
    run.add_argument("--enrich", dest="enrich", action="store_true", default=True, help="enrich with Semantic Scholar")
    run.add_argument("--no-enrich", dest="enrich", action="store_false", help="skip Semantic Scholar enrichment")
    run.add_argument("--report-limit", type=int, default=15, help="max papers in report")
    run.set_defaults(func=run_all)

    refresh = subparsers.add_parser("refresh", help="search, ingest, and report locally without Lark")
    refresh.add_argument("--query", default="3d-scene-editing", help="query profile or raw query")
    refresh.add_argument("--limit", type=int, default=20, help="max papers per source")
    refresh.add_argument("--sources", nargs="+", default=["arxiv", "cvf", "openreview"], choices=["arxiv", "cvf", "openreview"])
    refresh.add_argument("--delay", type=float, default=1.0, help="delay between API calls")
    refresh.add_argument("--timeout", type=int, default=15, help="network timeout per request")
    refresh.add_argument("--sample", action="store_true", help="use local sample data for offline tests")
    refresh.add_argument("--enrich", dest="enrich", action="store_true", default=True, help="enrich with Semantic Scholar")
    refresh.add_argument("--no-enrich", dest="enrich", action="store_false", help="skip Semantic Scholar enrichment")
    refresh.add_argument("--report-limit", type=int, default=15, help="max papers in report")
    refresh.set_defaults(func=refresh_local)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
