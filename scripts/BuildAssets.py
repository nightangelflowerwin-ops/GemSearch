"""Render small original vector-style spider icons with the standard library."""
import math
from pathlib import Path
import struct
import zlib

ROOT=Path(__file__).resolve().parents[1]
LEGS=[[(47,52),(27,30),(12,38)],[(46,58),(22,49),(6,60)],[(46,65),(22,76),(8,91)],[(49,70),(35,93),(25,104)]]
LEGS += [[(120-x,y) for x,y in leg] for leg in LEGS[:]]
def line(x,y,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)<1.8
def pixel(x,y):
    c=(17,24,13,255)
    if any(line(x,y,a,b) for leg in LEGS for a,b in zip(leg,leg[1:])):c=(187,247,123,255)
    for cy,rx,ry in [(43,23,30),(65,19,17)]:
        q=((x-60)/rx)**2+((y-cy)/ry)**2
        if q<1:c=(187,247,123,255) if q>.82 else (28,40,21,255)
    if abs(x-60)/9+abs(y-33)/15<1:c=(187,247,123,255)
    for cx in [53,67]:
        if (x-cx)**2+(y-65)**2<25:c=(236,255,220,255)
        if (x-cx-1)**2+(y-66)**2<4:c=(20,30,14,255)
    return c
def png(size):
    rows=[]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            colors=[pixel((x+(sx+.5)/2)*120/size,(y+(sy+.5)/2)*120/size) for sx in range(2) for sy in range(2)]
            row.extend(sum(c[i] for c in colors)//4 for i in range(4))
        rows.append(row)
    def chunk(k,b):return struct.pack('!I',len(b))+k+b+struct.pack('!I',zlib.crc32(k+b))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
if __name__=='__main__':
    target=ROOT/'extension/icons';target.mkdir(exist_ok=True)
    for size in [16,48,128]:(target/f'{size}.png').write_bytes(png(size))
    print('Generated 3 original spider icons.')
