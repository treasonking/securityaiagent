import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "scripts.manual_observation", *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )


def test_empty_note_and_exclusive_init(tmp_path):
    note = tmp_path / "private" / "first.json"
    assert cli("init", note, "--policy-memo", tmp_path / "absent.md").returncode == 0
    original = note.read_bytes()
    contents = json.loads(original.decode("utf-8"))
    assert contents.pop("own_test_data") is None
    assert set(contents.values()) == {""}
    result = cli("review", note)
    assert result.returncode == 0 and not result.stderr
    assert "정책 기록 · 프로그램명, 공식 정책 URL, 정책 확인일, 허용 자산" in result.stdout
    assert "관찰 기록 · 관찰 시각·시간대, 본인 소유 테스트 데이터 여부, 기대 동작, 직접 본 동작" in result.stdout
    assert "영향 기록 · 확인한 영향, 영향을 뒷받침하는 직접 근거" in result.stdout
    duplicate = cli("init", note)
    assert duplicate.returncode == 1 and "이미 노트가 있습니다" in duplicate.stderr
    assert note.read_bytes() == original


@pytest.mark.parametrize("different", [False, True], ids=["expected", "impact-unknown"])
def test_review_manual_observation(tmp_path, different):
    note = tmp_path / "first.json"
    memo = tmp_path / "selection.md"
    memo.write_text(
        "**첫 수동 참여는 가상정원을 추천한다.** [가상정원 공식 정책][g]\n"
        "2026년 1월 2일에 공개 정책과 범위 목록을 확인했다.\n"
        "[g]: https://garden.invalid/policy\n"
        "비공개 관찰 내용은 자동으로 복사하지 않는다.\n", encoding="utf-8",
    )
    assert cli("init", note, "--policy-memo", memo).returncode == 0
    data = json.loads(note.read_text(encoding="utf-8"))
    assert data["program"] == "가상정원"
    assert data["policy_url"] == "https://garden.invalid/policy"
    assert data["policy_checked_on"] == "2026-01-02"
    assert not data["observed_behavior"] and not data["allowed_asset"]
    data.update(allowed_asset="가상 작업 공간", observed_at="2026-01-02T14:00:00+09:00",
                own_test_data=True, expected_behavior="저장 완료 표시",
                observed_behavior="표시가 지연됨" if different else "저장 완료 표시",
                unconfirmed="저장 결과에 미친 영향" if different else "다른 화면의 동작")
    if not different:
        data.update(confirmed_impact="관찰한 화면에서 차이 없음", impact_basis="기대 문구와 표시 문구 일치")
    note.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
    original = note.read_bytes()
    result = cli("review", note)
    assert result.returncode == 0 and not result.stderr
    facts, gaps = result.stdout.split("빠진 항목\n")
    assert '기대 동작 · "저장 완료 표시"' in facts
    assert f'직접 본 동작 · "{data["observed_behavior"]}"' in facts
    if different:
        assert '미확인 사항 · "저장 결과에 미친 영향"' in facts
        assert "영향 기록 · 확인한 영향, 영향을 뒷받침하는 직접 근거" in gaps
        assert "확인한 영향 ·" not in facts
    else:
        assert '영향을 뒷받침하는 직접 근거 · "기대 문구와 표시 문구 일치"' in facts
        assert gaps.startswith("  없음\n")
    assert note.read_bytes() == original


def test_invalid_input_private_diagnostics_and_false_ownership(tmp_path):
    note = tmp_path / "note.json"
    note.write_text('{"private-marker":', encoding="utf-8")
    result = cli("review", note)
    assert result.returncode == 1 and not result.stdout
    assert "private-marker" not in result.stderr and str(note) not in result.stderr
    note.write_text('{"own_test_data": false}', encoding="utf-8")
    result = cli("review", note)
    assert result.returncode == 0 and "본인 소유 테스트 데이터 여부 · 아니요" in result.stdout


def test_recorded_impact_still_requires_separate_basis(tmp_path):
    note = tmp_path / "first.json"
    note.write_text('{"confirmed_impact":"합성 화면 표시 지연","impact_basis":"  "}', encoding="utf-8")
    result = cli("review", note)
    assert result.returncode == 0
    facts, gaps = result.stdout.split("빠진 항목\n")
    assert '확인한 영향 · "합성 화면 표시 지연"' in facts
    assert "영향 기록 · 영향을 뒷받침하는 직접 근거" in gaps


def test_note_in_repository_refused():
    note = ROOT / "manual-observation-test.json"
    result = cli("init", note)
    assert result.returncode == 1 and "Git 저장소 밖" in result.stderr
    assert not note.exists()
