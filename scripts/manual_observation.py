"""Create and review private, operator-written observations entirely offline."""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = {
    "program": "프로그램명",
    "policy_url": "공식 정책 URL",
    "policy_checked_on": "정책 확인일",
    "allowed_asset": "허용 자산",
}
OBSERVATION = {
    "observed_at": "관찰 시각·시간대",
    "own_test_data": "본인 소유 테스트 데이터 여부",
    "expected_behavior": "기대 동작",
    "observed_behavior": "직접 본 동작",
}
IMPACT = {"confirmed_impact": "확인한 영향", "impact_basis": "영향을 뒷받침하는 직접 근거"}
LIMITS = {"unconfirmed": "미확인 사항"}
FIELDS = POLICY | OBSERVATION | IMPACT | LIMITS


class NoteError(ValueError):
    """A message safe to print without disclosing note contents or file paths."""


def local_path(path: Path) -> Path:
    # Reject Windows network/device paths before asking the filesystem about them.
    if os.name == "nt" and (path.drive.startswith("\\\\") or path.is_reserved()
                            or ":" in str(path)[len(path.drive):]):
        raise NoteError("로컬 일반 파일을 지정하세요.")
    return path.expanduser()


def private_note(path: Path) -> Path:
    path = local_path(path)
    if path.suffix.lower() != ".json" or path.is_symlink():
        raise NoteError("저장소 밖의 일반 JSON 노트를 지정하세요.")
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT) or any((p / ".git").exists() for p in resolved.parents):
        raise NoteError("노트는 Git 저장소 밖의 비공개 폴더에 보관하세요.")
    return resolved


def public_policy(memo: Path) -> dict[str, str]:
    """Read only the public recommendation header, its policy link and review date."""
    try:
        lines = local_path(memo).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return {}
    intro = next((line for line in lines if line.startswith("**첫 수동 참여는 ")), "")
    selected = re.search(r"\[([^\[\]]+) 공식 정책\]\[([\w-]+)\]\s*$", intro)
    if not selected:
        return {}
    name, reference = selected.groups()
    if not re.match(r"^\*\*첫 수동 참여는 " + re.escape(name) + r"[을를] 추천", intro):
        return {}
    link = re.compile(r"\[" + re.escape(reference) + r"\]: (https://[^\s<>]+)")
    urls = [match[1] for line in lines if (match := link.fullmatch(line))]
    if len(urls) != 1:
        return {}
    result = {"program": name, "policy_url": urls[0]}
    for line in lines:
        checked = re.match(r"^(\d{4})년 (\d{1,2})월 (\d{1,2})일.*?공개 정책과 범위 목록을 확인", line)
        if checked:
            try:
                result["policy_checked_on"] = date(*map(int, checked.groups())).isoformat()
            except ValueError:
                pass
            break
    return result


def initialize(path: Path, memo: Path | None) -> None:
    note = dict.fromkeys(FIELDS, "")
    note["own_test_data"] = None
    if memo:
        note.update(public_policy(memo))
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(note, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("비공개 노트를 만들었습니다. 정책 정보와 관찰 내용을 직접 확인해 입력하세요.")


def review(path: Path) -> None:
    with path.open(encoding="utf-8-sig") as stream:
        note = json.load(stream)
    if not isinstance(note, dict) or note.keys() - FIELDS.keys():
        raise NoteError("지원하는 노트 필드와 JSON 형식을 확인하세요.")
    for key, value in note.items():
        if key == "own_test_data":
            if value is not None and not isinstance(value, bool):
                raise NoteError("본인 소유 여부는 true, false, null 중 하나로 입력하세요.")
        elif not isinstance(value, str):
            raise NoteError(f"{FIELDS[key]} 항목을 문자열로 입력하세요.")

    groups = (("정책 기록", POLICY), ("관찰 기록", OBSERVATION),
              ("영향 기록", IMPACT), ("미확인 사항", LIMITS))
    gaps = []
    for title, fields in groups:
        if fields is POLICY:
            print("정책 정보 · 원문과 직접 대조할 항목")
        elif fields is OBSERVATION:
            print("직접 기록한 내용")
        missing = []
        for key, label in fields.items():
            value = note.get(key)
            if value is None or isinstance(value, str) and not value.strip():
                missing.append(label)
                continue
            if isinstance(value, bool):
                display = "예" if value else "아니요"
            else:
                display = json.dumps(value, ensure_ascii=False)
            print(f"  {label} · {display}")
        if missing:
            gaps.append(f"  {title} · {', '.join(missing)}")
    print("빠진 항목")
    print("\n".join(gaps) if gaps else "  없음")
    print("이 검토는 기록의 빈칸만 확인합니다. 영향과 제보 여부는 사람이 판단합니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="새 비공개 JSON 노트 만들기")
    init.add_argument("note", type=Path)
    init.add_argument("--policy-memo", type=Path, help="선정 메모의 공개 정책 정보만 가져오기")
    commands.add_parser("review", help="기록한 내용과 빠진 항목 보기").add_argument("note", type=Path)
    args = parser.parse_args(argv)
    try:
        path = private_note(args.note)
        if args.command == "init":
            initialize(path, args.policy_memo)
        else:
            review(path)
    except FileExistsError:
        print("이미 노트가 있습니다. 기존 노트는 그대로 보존했습니다.", file=sys.stderr)
    except NoteError as exc:
        print(exc, file=sys.stderr)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OSError, RuntimeError):
        print("파일 접근 권한, UTF-8 인코딩과 JSON 형식을 확인하세요.", file=sys.stderr)
    else:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
