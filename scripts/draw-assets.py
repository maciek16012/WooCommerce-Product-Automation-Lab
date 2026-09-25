"""Original vector-like product illustrations, drawn locally with Pillow. MIT."""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets'; OUT.mkdir(exist_ok=True)
S=2
BG='#e9ebdf'; INK='#303c38'; LIGHT='#727e70'; PALE='#c1c9b8'; LIME='#c5d58d'
def canvas(): return Image.new('RGB',(1200,1000),BG)
def keyboard(im,box=(160,340,1040,700)):
    d=ImageDraw.Draw(im);x,y,x2,y2=box
    d.rounded_rectangle((x+12,y+21,x2+12,y2+21),radius=27,fill='#d1d6c6')
    d.rounded_rectangle(box,radius=24,fill=INK)
    cols,rows=15,5; gap=8; w=(x2-x-40)/cols; h=(y2-y-36)/rows
    for r in range(rows):
        for c in range(cols):
            if r==4 and 4<=c<=8: continue
            xx=x+20+c*w; yy=y+18+r*h
            d.rounded_rectangle((xx,yy,xx+w-gap,yy+h-gap),radius=5,fill=LIGHT if c!=14 else LIME)
            if r<4: d.line((xx+9,yy+9,xx+16,yy+9),fill='#c1c9b8',width=2)
    xx=x+20+4*w;yy=y+18+4*h
    d.rounded_rectangle((xx,yy,xx+5*w-gap,yy+h-gap),radius=5,fill=PALE)
    d.line((x+80,y,x+80,y-85,x+125,y-110,x+270,y-110),fill=INK,width=9)
def mouse(im,box=(405,245,795,755)):
    d=ImageDraw.Draw(im); x,y,x2,y2=box; mid=(x+x2)//2
    d.rounded_rectangle((x+14,y+23,x2+14,y2+23),radius=160,fill='#d0d6c5')
    d.rounded_rectangle(box,radius=150,fill=INK)
    d.line((mid,y-100,mid,y+170),fill='#73806d',width=5)
    d.line((x+10,y+205,x2-10,y+205),fill='#73806d',width=4)
    d.rounded_rectangle((mid-15,y+55,mid+15,y+140),radius=12,fill=LIME)
    d.line((mid,y-100,mid+100,y-140,mid+195,y-140),fill=INK,width=9)
    d.ellipse((mid-10,y2-100,mid+10,y2-80),fill=LIGHT)
def cable(im):
    d=ImageDraw.Draw(im)
    for a in range(3):
        d.arc((255+a*23,270+a*18,965-a*23,750-a*18),15,348,fill='#bcc3b3',width=25)
        d.arc((245+a*23,255+a*18,955-a*23,735-a*18),15,348,fill=INK,width=22)
    d.line((305,620,240,470,200,300),fill=INK,width=22)
    d.rounded_rectangle((160,205,239,350),radius=15,fill=INK)
    d.rounded_rectangle((175,152,224,222),radius=13,fill='#a9b2a4')
    d.rounded_rectangle((184,153,215,165),radius=4,fill=INK)
    d.rounded_rectangle((897,605,981,737),radius=15,fill=INK)
    d.rounded_rectangle((912,727,966,790),radius=13,fill='#a9b2a4')
    d.rounded_rectangle((921,773,957,786),radius=5,fill=INK)
    d.rounded_rectangle((555,294,637,432),radius=10,fill=LIME)
def hub(im):
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((225,420,1000,654),radius=35,fill='#ccd2c1')
    d.rounded_rectangle((205,390,980,624),radius=30,fill=INK)
    d.polygon([(225,390),(275,325),(945,325),(980,390)],fill='#667360')
    for x in (300,475,650,825):
        d.rounded_rectangle((x,446,x+94,503),radius=5,fill='#9ba894')
        d.rectangle((x+9,458,x+85,489),fill='#26322e')
        d.line((x+22,491,x+74,491),fill=LIME,width=5)
    d.line((225,489,150,475,112,350,150,245,255,222),fill=INK,width=16)
    d.rounded_rectangle((247,194,342,246),radius=13,fill=INK)
    d.rounded_rectangle((330,204,385,236),radius=8,fill='#a7b19e')
    d.ellipse((910,552,919,561),fill=LIME)
def stand(im):
    d=ImageDraw.Draw(im)
    d.ellipse((145,690,1075,830),fill='#d1d4c6')
    d.polygon([(210,500),(285,500),(285,738),(210,768)],fill=INK)
    d.polygon([(906,420),(970,410),(970,679),(906,704)],fill=INK)
    d.polygon([(155,436),(775,244),(1060,438),(432,651)],fill='#d1b994')
    d.polygon([(155,436),(432,651),(432,690),(155,475)],fill='#a48d70')
    d.polygon([(432,651),(1060,438),(1060,478),(432,690)],fill='#baa17e')
    for i in range(4): d.line((230+i*47,430,775+i*28,284),fill='#c2a780',width=2)
    d.polygon([(645,443),(716,419),(776,464),(701,489)],fill='#c5ad89')
def clips(im):
    d=ImageDraw.Draw(im)
    for i,(x,y) in enumerate([(240,390),(450,310),(660,390),(425,555)]):
        d.rounded_rectangle((x+10,y+22,x+190,y+165),radius=45,fill='#c8cfbc')
        d.rounded_rectangle((x,y,x+180,y+145),radius=45,fill=INK if i%2==0 else '#859176')
        d.rounded_rectangle((x+63,y-5,x+117,y+75),radius=24,fill=BG)
        d.line((x+89,y+40,x+89,y+235),fill=LIME if i%2==0 else PALE,width=18)
        d.line((x+89,y+40,x+89,y-80),fill=LIME if i%2==0 else PALE,width=18)
for name,fn in [('keyboard',keyboard),('mouse',mouse),('cable',cable),('hub',hub),('stand',stand),('clips',clips)]:
    im=canvas();fn(im);im.save(OUT/(name+'.png'),optimize=True)
# A composed editorial desk illustration, no photos or external assets.
im=Image.new('RGB',(1200,1100),'#e5e9dc');d=ImageDraw.Draw(im)
d.ellipse((35,145,1130,1100),fill='#d8decd')
d.polygon([(60,430),(660,155),(1200,450),(572,835)],fill='#c9b28e')
d.polygon([(60,430),(572,835),(572,879),(60,473)],fill='#af9877')
d.polygon([(572,835),(1200,450),(1200,492),(572,879)],fill='#bda27e')
d.polygon([(155,580),(198,612),(198,995),(155,968)],fill=INK)
d.polygon([(1030,587),(1073,563),(1073,952),(1030,980)],fill=INK)
d.polygon([(534,850),(577,880),(577,1080),(534,1060)],fill=INK)
# monitor, stand, and screen
d.polygon([(463,408),(634,361),(709,406),(539,461)],fill=INK)
d.rectangle((561,280,601,423),fill='#64705e')
d.rounded_rectangle((347,157,919,401),radius=15,fill=INK)
d.rounded_rectangle((366,175,900,377),radius=5,fill='#c5d58d')
d.ellipse((550,180,816,378),fill='#acbd72');d.rectangle((398,216,552,224),fill=INK);d.rectangle((398,238,514,242),fill='#687a44')
d.rectangle((398,312,472,335),fill=INK)
# desktop mat
d.rounded_rectangle((297,480,962,753),radius=25,fill='#8b967f')
keyboard(im,(333,534,732,710));mouse(im,(791,520,913,694))
# cup and plant
d.ellipse((137,465,249,527),fill='#a69072');d.rounded_rectangle((142,385,242,492),radius=22,fill='#e9edde');d.ellipse((143,365,242,409),fill='#d7dcc9');d.ellipse((155,375,228,397),fill='#61704e')
d.rounded_rectangle((970,297,1090,401),radius=20,fill='#dddac6')
for x,y in [(992,190),(1050,157),(1100,212),(966,225)]:
    d.line((1030,330,x,y),fill='#6c7c4f',width=8);d.ellipse((x-25,y-38,x+24,y+25),fill='#758652')
im.save(OUT/'hero.png',optimize=True)
print('Created 7 original PNG illustrations')
