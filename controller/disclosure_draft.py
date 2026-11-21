"""Internal review copy, derived exclusively from a verified operator report."""
import hashlib
import json

TEMPLATE = 'internal-disclosure-ko-v1'


def render_review(view, input_hashes):
    ids = [row['evidence_id'] for row in view['evidence']]
    groups = [
        ('관측 전후에 두 계정의 신원이 각각 유지됐다.', (2, 3, 9, 10)),
        ('각 소유자의 비공개 리소스는 반복 조회에서 같은 합성 값을 반환했고, 두 소유자의 값은 서로 달랐다.', (4, 5, 7, 8)),
        ('계정 A가 받은 응답의 합성 값이 계정 B 소유자의 대조 응답과 일치했다.', (6, 5, 7)),
    ]
    refs = '\n'.join(f"- {description} 근거: " + ', '.join(f"`{ids[i]}`" for i in indices)
                     for description, indices in groups)
    markdown = f"""# 내부 검토 초안 · 다른 계정의 비공개 리소스 조회

로컬 합성 사례 · 제출 전 검토용

## 검사 범위

저장 검사 `{view['run_id']}` · 등록 대상 `{view['policy']['target_id']}` · `operator-resource-v1`.
준비된 계정 A와 B, 각 계정이 소유한 비공개 리소스 한 건씩을 확인했다.

## 관측된 영향

계정 A가 계정 B 소유의 비공개 리소스를 조회했을 때 HTTP 200을 받았다.
응답에서 확인한 합성 값은 B가 자기 리소스를 조회했을 때의 값과 일치했다.
이 두 계정과 리소스에 대한 저장 증거의 재판정은 최초 판정과 같은 `VULNERABLE`이다.

## 관련 증거

{refs}

## 한계

이 기록은 해당 실행 시점의 두 합성 리소스에 한정된다. 다른 계정·리소스, 실제 고객 데이터와 피해 범위는 확인하지 않았다.

## 수정 권고

비공개 리소스를 반환하기 전에 서버에서 인증된 계정이 해당 객체를 읽을 권한이 있는지 확인한다.
수정 확인 시 소유자 조회는 성공하고 권한이 없는 계정의 조회는 거절되는지 함께 확인한다.
"""
    binding = dict(template=TEMPLATE, run_id=view['run_id'], conclusion=view['conclusion'],
                   evidence_ids=ids, inputs=input_hashes, markdown=markdown)
    encoded = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return dict(run_id=view['run_id'], template_version=TEMPLATE, markdown=markdown,
                review_digest=hashlib.sha256(encoded).hexdigest())
