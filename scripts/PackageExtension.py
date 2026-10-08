"""Package ONLY extension assets; no environment, wallet or local data files."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
FILES=['manifest.json','background.js','shared.js','content.js','SpiderUi.js','popup.html','popup.css','popup.js','icons/16.png','icons/48.png','icons/128.png']
def package(target=None):
    target=target or ROOT/'dist/GemSearchExtension.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT/'extension'/name,name)
    return target
if __name__=='__main__':print(package())
