# Angela Backend

队友 B 的后端音频管线与运行时服务。

## Run

```bash
cd packages/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

接口：

- `GET /api/songs`
- `GET /api/songs/{id}`
- `GET /assets/{path}`
- `POST /api/tts`
- `WS /ws`

没有 `assets/songs/*` 时，服务会用 `data/samples` 作为兜底数据；放入真实
`assets/songs/daoxiang/song.json` 和轨道文件后自动优先使用真实素材。

## Offline Tools

```bash
python rvc.py assets/songs/daoxiang/vocals_angela.wav assets/songs/daoxiang/vocals_angela_rvc.wav \
  --model assets/models/angela_v1.pth --index assets/models/angela.index

python mix.py assets/songs/daoxiang/instrumental.wav assets/songs/daoxiang/vocals_angela_rvc.wav \
  assets/songs/daoxiang/vocals_neo.wav assets/songs/daoxiang/mix.wav

python bake.py assets/songs/daoxiang/vocals_angela_rvc.wav assets/songs/daoxiang/visemes.json \
  --song daoxiang
```
