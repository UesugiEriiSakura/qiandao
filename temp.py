import cv2
import numpy as np
import os
import shutil

def solve_slide_captcha_final(mark_path, bg_path, output_dir='debug_final1'):
    # --- 0. 准备工作 ---
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    print(f"创建调试目录: {output_dir}/")

    # 使用 IMREAD_UNCHANGED 读取，以防图片包含透明通道(Alpha)
    mark = cv2.imread(mark_path, cv2.IMREAD_UNCHANGED)
    bg = cv2.imread(bg_path)
    
    if mark is None or bg is None:
        print("错误：无法读取图片")
        return

    cv2.imwrite(f'{output_dir}/00_mark_original.png', mark)

    # =========================================================
    # Step 1: 完美提取滑块形状 (修改版)
    # =========================================================
    print("Step 1: 提取滑块形状...")
    
    # 判断是否包含 Alpha 通道 (透明背景)
    if mark.shape[2] == 4:
        # 如果是 PNG 透明图，直接取第4个通道(Alpha)作为掩码
        print("检测到透明通道，直接使用Alpha层")
        mask = mark[:, :, 3]
    else:
        # 如果是 JPG 或黑底图，转灰度后取阈值
        print("未检测到透明通道，使用灰度阈值法")
        mark_gray = cv2.cvtColor(mark, cv2.COLOR_BGR2GRAY)
        # 只要像素值大于 10 (不是纯黑)，就认为是滑块的一部分
        _, mask = cv2.threshold(mark_gray, 10, 255, cv2.THRESH_BINARY)
    
    cv2.imwrite(f'{output_dir}/01_mark_mask_fixed.png', mask)

    # 寻找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("错误：无法提取滑块轮廓")
        return
    
    # 取最大轮廓
    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    print(f"   滑块尺寸: {w}x{h}")

    # 裁切掩码作为模板
    template_roi = mask[y:y+h, x:x+w]
    
    # 提取边缘 (Canny)
    # 因为现在的 mask 是纯白形状，Canny 提取出的边缘会非常完美
    template_edge = cv2.Canny(template_roi, 100, 200)
    cv2.imwrite(f'{output_dir}/02_template_edge_clean.png', template_edge)

    # =========================================================
    # Step 2: 背景处理 (保持之前的优秀逻辑)
    # =========================================================
    print("Step 2: 处理背景...")
    
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    
    # 直方图均衡化 (增强缺口阴影对比度)
    bg_eq = cv2.equalizeHist(bg_gray)
    cv2.imwrite(f'{output_dir}/03_bg_equalized.png', bg_eq)
    
    # 边缘检测
    bg_edge = cv2.Canny(bg_eq, 50, 200)
    cv2.imwrite(f'{output_dir}/04_bg_edges.png', bg_edge)
    
    # 锁定Y轴区域 (Strip Search)
    search_y_start = max(0, y - 10)
    search_y_end = min(bg_edge.shape[0], y + h + 10)
    bg_strip = bg_edge[search_y_start:search_y_end, :]
    cv2.imwrite(f'{output_dir}/05_bg_strip.png', bg_strip)

    # =========================================================
    # Step 3: 匹配
    # =========================================================
    print("Step 3: 匹配中...")
    
    res = cv2.matchTemplate(bg_strip, template_edge, cv2.TM_CCOEFF_NORMED)
    
    # 屏蔽左侧区域 (防止匹配到滑块起始位置)
    # 屏蔽宽度设为滑块宽度的 1.2 倍
    safe_margin = int(w * 1.2)
    if res.shape[1] > safe_margin:
        res[:, :safe_margin] = -1.0
        
    # 可视化热力图
    res_vis = cv2.normalize(res, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    cv2.imwrite(f'{output_dir}/06_match_heatmap.png', res_vis)
    
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    best_x = max_loc[0]
    best_y = search_y_start + max_loc[1]

    # =========================================================
    # Step 4: 输出结果
    # =========================================================
    result_img = bg.copy()
    cv2.rectangle(result_img, (best_x, best_y), (best_x + w, best_y + h), (0, 0, 255), 2)
    
    # 画一下搜索区域辅助线
    cv2.rectangle(result_img, (0, search_y_start), (bg.shape[1], search_y_end), (0, 255, 0), 1)
    
    output_path = f'{output_dir}/RESULT_FINAL.png'
    cv2.imwrite(output_path, result_img)
    
    print("-" * 30)
    print(f"【最终结果】")
    print(f"缺口坐标: X={best_x}")
    print(f"结果保存在: {output_path}")
    print("-" * 30)

    return best_x

if __name__ == '__main__':
    solve_slide_captcha_final('mark.png', 'bg.png')