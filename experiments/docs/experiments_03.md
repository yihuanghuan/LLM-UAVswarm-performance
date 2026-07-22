# 5. 实验 3：目标编队几何生成正确性测试

## 目的

证明 LFS 可以稳定编译成几何目标点，而不是只解析文本。

## 实验设计

输入不同 formation：

| Formation | 参数 |
| --- | --- |
| Circle | center + radius + N |
| Line | center + spacing + N |
| Sphere | center + radius + N |
| Free | 返回初始点或指定点 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| generated target points | 生成的目标点 |
| center error | 目标点平均中心与指定中心误差 |
| radius error | 圆形/球形半径误差 |
| spacing error | 直线间距误差 |
| shape validity | 是否满足几何约束 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| 2D scatter plot | 圆形、直线目标点 |
| 3D scatter plot | 球形目标点 |
| Table | center error / radius error / spacing error |

这个实验不一定要作为主实验，可以放在 supplementary 或 appendix，但它能支撑系统完整性。
