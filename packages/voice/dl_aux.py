from huggingface_hub import hf_hub_download
import os
out = r'D:/ExWorld/Github/Angela/packages/voice/aux_models'
os.makedirs(out, exist_ok=True)
for f in ['hubert_base.pt', 'rmvpe.pt', 'rmvpe.onnx']:
    try:
        p = hf_hub_download('Daswer123/RVC_Base', f, local_dir=out)
        print('OK', f, round(os.path.getsize(p)/1048576, 1), 'MB')
    except Exception as e:
        print('FAIL', f, str(e)[:150])
