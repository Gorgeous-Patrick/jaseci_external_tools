"""Editable schematic: Jac graph nodes contain ability dependency graphs."""
from pathlib import Path
import os
OUT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR','/tmp/ttg-dependency-diagram-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','pdf.fonttype':42})

def build_figure():
    fig,ax=plt.subplots(figsize=(16,9));fig.subplots_adjust(0,0,1,1)
    ax.set_xlim(0,1600);ax.set_ylim(1000,0);ax.axis('off');fig.patch.set_facecolor('white')
    ink='#20364a';blue='#126da3';bluefill='#e8f4fc';line='#b7cbd9';gray='#f1f3f5';muted='#526b7e'
    def box(x,y,w,h,text='',fc='white',ec=line,fs=17,lw=1.5,style='solid',weight='normal'):
     p=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=13',facecolor=fc,edgecolor=ec,linewidth=lw,linestyle=style,zorder=2);ax.add_patch(p)
     if text:ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=fs,color=ink,weight=weight,zorder=5,linespacing=1.35)
     return p
    def arrow(a,b,color=ink,lw=1.8,style='solid',rad=0,z=4):
     ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=16,color=color,linewidth=lw,linestyle=style,connectionstyle=f'arc3,rad={rad}',zorder=z))
    def region(x,y,w,h,label):
     box(x,y,w,h,fc=bluefill,ec=blue,lw=1.6,style=(0,(5,3)))
     ax.text(x+16,y+23,label,fontsize=13,color=blue,weight='bold',va='center',zorder=5)
    def outer(x,y,w,h,title,ability):
     box(x,y,w,h,ec=ink,lw=2.2)
     ax.text(x+24,y+32,title,fontsize=22,weight='bold',color=ink,zorder=5)
     ax.text(x+w-24,y+32,ability,fontsize=17,color=muted,ha='right',zorder=5)
    ax.text(65,60,'Jac Graph with an ability dependency graph inside each node',fontsize=28,weight='bold',color=ink)
    ax.text(65,99,'Example: A visits [B, C]; B and C each read and report their own value.',fontsize=18,color=muted)
    # Outer data graph. A's ability queues its two children; native execution is B then C.
    outer(430,145,740,320,'Node A','A.entry')
    outer(65,595,690,285,'Node B','B.entry')
    outer(845,595,690,285,'Node C','C.entry')
    # Region fragment in A and the external binding checkpoint.
    box(455,220,155,68,'A.id\nknown input',fc=gray,fs=16)
    ax.text(532,204,'CHECKPOINT',ha='center',fontsize=12,weight='bold',color=muted,zorder=5)
    region(645,200,500,125,'R1 · path discovery')
    box(665,243,240,56,'Resolve A.children',ec=blue,fs=17)
    box(950,243,175,56,'IDs: B, C',ec=blue,fs=17)
    arrow((610,254),(665,271));arrow((905,271),(950,271),color=blue)
    box(900,365,225,62,'Enqueue [B, C]',fc=gray,fs=17)
    arrow((1037,299),(1012,365))
    ax.text(463,400,'Native queue order is retained.',fontsize=16,color=muted,zorder=5)
    # Actual Jac edges are deliberately distinct from value-flow arrows.
    arrow((630,465),(410,595),lw=3)
    arrow((970,465),(1190,595),lw=3)
    ax.text(345,530,'Jac edge A → B',fontsize=16,color=ink,rotation=0,ha='center',zorder=5)
    ax.text(1255,530,'Jac edge A → C',fontsize=16,color=ink,ha='center',zorder=5)
    # Intra-ability dependency graphs: SQL-produced child identity to payload read;
    # report nodes stay native. Matching R1 labels show one composed query.
    for x,name in [(65,'B'),(845,'C')]:
     region(x+24,650,642,115,'R1 · payload read')
     box(x+45,693,210,52,f'{name}.id\nfrom A.children',ec=blue,fs=15)
     box(x+336,693,286,52,f'Read {name}.value',ec=blue,fs=18)
     arrow((x+255,719),(x+336,719),color=blue)
     box(x+336,797,286,55,f'Report {name}.value',fc=gray,fs=18)
     arrow((x+479,745),(x+479,797))
    # Explanation outside the Jac nodes.
    box(65,910,26,22,fc=bluefill,ec=blue,lw=1.5,style=(0,(4,2)))
    ax.text(105,927,'R1 (one SQL query): discover children + fetch values',fontsize=16,color=ink)
    box(760,910,26,22,fc=gray,ec=line)
    ax.text(800,927,'Native: enqueue, ability execution and ordered reports',fontsize=16,color=ink)
    ax.text(65,966,'No B→C future-access dependency in this example. Conceptual fanout composition; current typed region kernel is single-successor.',fontsize=13,color=muted)
    return fig
