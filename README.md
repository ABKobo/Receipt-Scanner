# Receipt Scanner

FastAPI와 EasyOCR(한국어·영어)로 영수증에서 날짜와 품목/가격을 추출하는 최소 웹앱입니다. 이미지와 결과를 서버에 영구 저장하지 않습니다.

## Windows 실행

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. 첫 OCR 요청 시 모델 다운로드와 초기화로 시간이 걸릴 수 있으며 GPU 없이 CPU로 실행합니다.

## 테스트

```powershell
pytest -q
```

GitHub push 시 `.github/workflows/test.yml`이 기본 테스트를 실행합니다.

## GitHub 및 배포

`git init`, `git add .`, `git commit -m "Build receipt scanner MVP"`, `git branch -M main`, `git remote add origin https://github.com/<OWNER>/<REPO>.git`, `git push -u origin main` 순서로 올립니다. Render에서 저장소를 연결하면 `render.yaml`로 서비스가 생성됩니다. 배포 완료 후 Render 대시보드의 서비스 URL이 공개 URL입니다.

## 검증 범위와 미해결 사항

API 테스트는 파서, 잘못된 파일 형식, CSV 응답을 자동 검증합니다. 실제 브라우저 업로드/OCR/복사/다운로드는 이 환경에 샘플 영수증과 실행 중 서버가 없어 완료했다고 보고하지 않습니다. EasyOCR 모델 다운로드 시간과 무료 호스팅 메모리 제한은 실제 배포 환경에서 확인해야 하며, 복잡한 줄바꿈 영수증은 수동 수정이 필요할 수 있습니다.
