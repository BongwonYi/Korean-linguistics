"""syntax-analyzer 폴더를 Hugging Face Space에 올린다(git 비밀번호 창 없이 Hub API 사용).

- 토큰: Windows 자격 증명 관리자(keyring 서비스 'huggingface', 이름 'api_key') → 없으면 환경 변수 HF_TOKEN.
  토큰 값은 화면이나 파일에 쓰지 않는다.
- README.md 머리말(sdk: docker 등)은 이 폴더의 README에 들어 있어야 한다.

실행(syntax-analyzer 폴더에서): python -m tools.deploy_space [--space bongwonyi/syntax-analyzer] [--dry-run]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE = sys.argv[sys.argv.index("--space") + 1] if "--space" in sys.argv else "bongwonyi/syntax-analyzer"
IGNORE = ["**/__pycache__/**", "**/*.pyc", ".pytest_cache/**", "**/.DS_Store"]


def get_token():
    try:
        import keyring
        t = keyring.get_password("huggingface", "api_key")
        if t:
            return t.strip()
    except Exception:
        pass
    return os.environ.get("HF_TOKEN", "").strip()


def main():
    head = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:10]
    if not head or head[0] != "---" or not any(line.startswith("sdk:") for line in head):
        print("README.md 맨 위에 Space 설정 머리말(--- … sdk: docker … ---)이 없습니다. 중단합니다.")
        return 2
    if "--dry-run" in sys.argv:
        print(f"올릴 폴더: {ROOT} → spaces/{SPACE}")
        return 0
    token = get_token()
    if not token:
        print("Hugging Face 토큰이 없습니다. 평가세트/set_key.py huggingface 로 저장해 주세요.")
        return 2
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    who = api.whoami()["name"]
    info = api.upload_folder(folder_path=str(ROOT), repo_id=SPACE, repo_type="space",
                             ignore_patterns=IGNORE, commit_message="논항 구조 분석과 화면 추가")
    print(f"올림 완료({who}): {info.commit_url if hasattr(info, 'commit_url') else info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
