"""行业板块涨跌排行图 -> 企业微信图片推送。

数据源: 东财行业板块 (akshare), 失败回退同花顺行业板块。
输出: 涨跌幅 TOP10 / BOTTOM10 横向条形图(PNG) + 简短文字摘要。
"""
import base64
import hashlib
import io
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import requests

RED = "#d92626"   # 涨
GREEN = "#0a9c69"  # 跌


def setup_font():
    for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]:
        if os.path.exists(p):
            try:
                font_manager.fontManager.addfont(p)
                name = font_manager.FontProperties(fname=p).get_name()
                plt.rcParams["font.family"] = name
                print("使用字体:", p, name)
                return
            except Exception as e:
                print("字体加载失败", p, e)
    print("!! 未找到中文字体,图表中文可能乱码")


def fetch_sector():
    import akshare as ak
    df = None
    # 1) 东财行业板块
    for fn in ["stock_board_industry_name_em", "stock_board_industry_summary_em"]:
        f = getattr(ak, fn, None)
        if not f:
            continue
        for attempt in range(3):
            try:
                df = f()
                if df is not None and len(df):
                    print(f"数据源 {fn}: {len(df)} 行, 列: {list(df.columns)}")
                    return df
            except Exception as e:
                print(f"{fn} 失败 {attempt+1}: {type(e).__name__} {str(e)[:120]}")
                time.sleep(3)
    # 2) 同花顺行业板块
    f = getattr(ak, "stock_board_industry_summary_ths", None)
    if f:
        try:
            df = f()
            print("数据源 stock_board_industry_summary_ths:", len(df), "行, 列:", list(df.columns))
            return df
        except Exception as e:
            print("ths 失败:", type(e).__name__, str(e)[:120])
    return None


def pick_columns(df):
    cols = list(df.columns)
    name_col = next((c for c in cols if ("板块" in c and "名称" in c)
                     or c in ("名称", "行业名称", "板块名称", "板块")), None)
    if not name_col:
        name_col = next((c for c in cols if "名称" in c or "板块" in c), None)
    chg_col = next((c for c in cols if "涨跌幅" in c), None)
    up_col = next((c for c in cols if "上涨家数" in c), None)
    down_col = next((c for c in cols if "下跌家数" in c), None)
    print("选中列: 名称=", name_col, "涨跌幅=", chg_col)
    return name_col, chg_col, up_col, down_col


def main():
    setup_font()
    df = fetch_sector()
    if df is None or len(df) == 0:
        print("!! 数据获取失败,退出(不影响仓库)")
        return

    name_col, chg_col, up_col, down_col = pick_columns(df)
    if not name_col or not chg_col:
        print("!! 找不到名称/涨跌幅列,退出")
        return

    rows = []
    for _, r in df.iterrows():
        try:
            pct = float(str(r[chg_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue
        rows.append({"name": str(r[name_col]), "pct": pct})

    rows.sort(key=lambda x: x["pct"], reverse=True)
    top = rows[:10]
    bot = rows[-10:][::-1]
    show = top + bot
    names = [f"{x['name']}" for x in show]
    pcts = [x["pct"] for x in show]
    colors = [RED if p >= 0 else GREEN for p in pcts]

    # 涨跌家数统计
    up_sum = down_sum = None
    if up_col and down_col:
        try:
            up_sum = int(df[up_col].dropna().astype(float).sum())
            down_sum = int(df[down_col].dropna().astype(float).sum())
        except Exception:
            pass

    fig, ax = plt.subplots(figsize=(9, 10.5), facecolor="white")
    y = list(range(len(names)))[::-1]
    ax.barh(y, pcts, color=colors, height=0.62)
    for yi, p in zip(y, pcts):
        ax.text(p + (0.12 if p >= 0 else -0.12), yi, f"{p:+.2f}%",
                va="center", ha="left" if p >= 0 else "right",
                fontsize=11, color=colors[len(y) - 1 - yi])
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=12)
    ax.axvline(0, color="#999", lw=0.8)
    ax.set_xlabel("涨跌幅 %", fontsize=11)
    ax.grid(axis="x", color="#eee", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    t = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    title = f"A股行业板块涨跌榜 {t}"
    if up_sum is not None:
        title += f" ｜ 上涨 {up_sum} 家 / 下跌 {down_sum} 家"
    ax.set_title(title, fontsize=15, pad=14)
    fig.text(0.99, 0.01, "数据来源: 东方财富/同花顺行业板块 · 仅供参考",
             ha="right", fontsize=8, color="#999")

    buf = io.BytesIO()
    dpi = 110
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    img = buf.read()
    print("图片大小:", len(img), "字节")
    if len(img) > 2 * 1024 * 1024:
        # 超过企业微信 2MB 限制,降分辨率重存
        buf2 = io.BytesIO()
        fig2, ax2 = plt.subplots(figsize=(8, 9), facecolor="white")
        ax2.barh(y, pcts, color=colors, height=0.62)
        ax2.set_yticks(y)
        ax2.set_yticklabels(names, fontsize=11)
        ax2.axvline(0, color="#999", lw=0.8)
        ax2.set_title(title, fontsize=13, pad=10)
        fig2.savefig(buf2, format="png", dpi=72, bbox_inches="tight", facecolor="white")
        plt.close(fig2)
        buf2.seek(0)
        img = buf2.read()
        print("降采样后大小:", len(img))

    webhook = os.environ.get("WECHAT_WEBHOOK_URL", "")
    if not webhook:
        print("!! 未配置 WECHAT_WEBHOOK_URL,只生图不推送")
        return

    b64 = base64.b64encode(img).decode()
    md5 = hashlib.md5(img).hexdigest()
    r = requests.post(webhook, json={
        "msgtype": "image",
        "image": {"base64": b64, "md5": md5},
    }, timeout=30)
    print("微信图片推送:", r.status_code, r.text[:200])

    # 简短文字摘要
    lines = ["📊 领涨板块", *[f"{x['name']} {x['pct']:+.2f}%" for x in top[:3]],
             "📉 领跌板块", *[f"{x['name']} {x['pct']:+.2f}%" for x in bot[:3]]]
    r2 = requests.post(webhook, json={
        "msgtype": "text",
        "text": {"content": "\n".join(lines)},
    }, timeout=30)
    print("微信文字推送:", r2.status_code, r2.text[:200])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("!! 未捕获异常(不影响仓库):", type(e).__name__, str(e)[:300])
        sys.exit(0)
