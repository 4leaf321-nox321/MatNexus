"""카드 여럿을 **한 묶음으로** 내보낸다 — 덱 파일 + manifest + 체크섬.

## 왜 번들인가

해석 하나에 재료가 여럿 들어간다. 지금은 카드를 **한 장씩** 내려받아 사람이 폴더에
모으고, 그 묶음이 무엇이었는지는 아무 데도 안 남는다.

해석자가 물을 것은 하나다 — **「내가 받은 이 덱이 그때 그 카드가 맞나」.** 답할 방법이
없으면 덱을 다시 받는 것 말고 길이 없고, 다시 받는 사이에 카드가 바뀌었을 수도 있다.

그래서 묶음마다 적어 둔다.

    manifest.json   무엇을 · 어떤 형식으로 · 어느 단위계로 · 누가 · 언제
    SHA256SUMS      덱 파일마다의 해시. 받은 쪽이 그대로 검산한다
    decks/          덱 파일들

## 덱 바이트는 결정적이다

같은 카드·형식·단위계면 **덱 파일의 내용이 항상 같다.** 그래야 체크섬이 뜻을 갖는다.

압축 파일 자체는 매번 조금 다르다 — `manifest.json` 에 내보낸 시각과 사람이 들어가기
때문이다. **그것을 빼지 않는다**: 「언제 누가 뽑은 묶음인가」 가 근거의 절반이고,
검산에 쓰는 것은 덱의 해시지 압축 파일의 해시가 아니다.

압축 항목의 **시각은 고정**한다(1980-01-01). 안 그러면 같은 내용도 파일마다 mtime 이
달라 diff 가 안 된다.

## 초안도 담는다 — 다만 적어 둔다

확정 전에 덱에 넣어 한 번 돌려 보는 것이 검토의 실체다(카드 한 장 내보내기와 같은
판단). 대신 manifest 와 경고에 **초안 몇 장이 들어 있는지** 남긴다.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime

from matcore import export

#: 압축 항목의 고정 시각. 같은 내용이면 같은 바이트가 되도록.
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class BundleCard:
    """묶음에 담길 카드 하나 — 덱과 그 이름표."""

    card_id: str
    label: str
    material: str
    status: str
    deck: export.Deck


@dataclass(frozen=True)
class Bundle:
    content: bytes
    filename: str
    warnings: tuple[str, ...]


def _unique(name: str, taken: set[str]) -> str:
    """같은 이름이 둘이면 뒤에 번호를 붙인다.

    **덮어쓰지 않는다.** 재료 이름이 같은 카드가 둘 있을 수 있고(방향이 다르거나
    확정과 초안이 함께), 그때 하나가 사라지면 받는 쪽은 그 사실을 모른다.
    """
    if name not in taken:
        taken.add(name)
        return name
    stem, _, suffix = name.rpartition(".")
    for index in range(2, 100):
        candidate = f"{stem}_{index}.{suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise export.ExportError(f"이름이 너무 많이 겹칩니다: {name}")


def build(
    cards: list[BundleCard],
    *,
    target: export.Renderer,
    units: str,
    exported_by: str,
    app_version: str,
    now: datetime,
) -> Bundle:
    """묶음 하나를 만든다. 덱 렌더링은 부르는 쪽이 끝내서 넘긴다.

    **정렬해서 담는다** — 재료·이름·id 순. 고른 순서대로 담으면 같은 묶음도 화면에서
    고른 순서에 따라 파일 차례가 달라져, diff 가 매번 통째로 바뀐다.
    """
    # **렌더러는 부르는 쪽이 고른다.** DB 정의로 만든 렌더러도 있어서
    # (`fitting/renderers.py`) 키만으로는 여기서 못 찾는다.
    system = export.systems.get(units)

    ordered = sorted(cards, key=lambda one: (one.material, one.label, one.card_id))
    entries: list[dict[str, object]] = []
    files: list[tuple[str, str]] = []
    taken: set[str] = set()
    notes: list[str] = []

    for card in ordered:
        rendered = export.render(target, card.deck, system)
        name = _unique(
            f"decks/{card.deck.name}{target.suffix}_{system.key}.{target.extension}", taken
        )
        digest = hashlib.sha256(rendered.text.encode("utf-8")).hexdigest()
        files.append((name, rendered.text))
        entries.append(
            {
                "card_id": card.card_id,
                "label": card.label,
                "material": card.material,
                "status": card.status,
                "file": name,
                "sha256": digest,
                # **내보내면서 한 일이 따라간다.** 「조용히 하지 않았다」 는 증거다.
                "notes": list(rendered.notes),
            }
        )
        notes.extend(rendered.notes)

    drafts = [one for one in ordered if one.status == "draft"]
    warnings: list[str] = []
    if drafts:
        # **초안이 섞였다는 사실이 묶음 밖에서도 보여야 한다.** 덱 안 주석은 파일을
        # 열어야 보이고, 안 여는 사람이 있다.
        warnings.append(
            f"초안 {len(drafts)}장이 들어 있습니다: "
            + ", ".join(f"{one.material} · {one.label}" for one in drafts)
        )

    manifest = {
        "kind": "matnexus.card-bundle",
        "version": 1,
        "exported_at": now.isoformat(),
        "exported_by": exported_by,
        "app_version": app_version,
        "format": target.key,
        "units": system.key,
        "cards": entries,
        "warnings": warnings,
    }

    sums = "".join(f"{one['sha256']}  {one['file']}\n" for one in entries)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in [
            ("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
            ("SHA256SUMS", sums),
            *files,
        ]:
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            # 유닉스에서 풀어도 읽을 수 있는 권한.
            info.external_attr = 0o644 << 16
            archive.writestr(info, text)

    stamp = now.strftime("%Y%m%d")
    return Bundle(
        content=buffer.getvalue(),
        filename=f"matnexus_cards_{target.key}_{system.key}_{stamp}.zip",
        warnings=tuple(warnings),
    )
