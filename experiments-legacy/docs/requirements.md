## 1.版本控制
请以当前仓库中的 `gazebo-experiment-v1` 标签对应的版本作为固定基础版本，为每个实验分别创建独立分支。

要求：

0. 绝对不允许对`gazebo-experiment-v1`的代码进行任何修改，只允许在完成实验并获得实验数据后将本次实验结果（包括但不限于：实验记录文档、图表、视频、原始数据、rosbag等）放入src/LLM-UAVswarm-performance/experiments/results文件夹，命名方式为“/results/experiments_xx”。
1. 每个实验都必须从 `gazebo-experiment-v1` 创建新分支，不要从上一个实验分支继续开发；
2. 分支命名统一，例如：
   - `exp/01-llm-parsing`
   - `exp/04-assignment-baselines`
   - `exp/08-iapf`
3. 只在当前实验分支中加入该实验需要的评估脚本、baseline、消融开关、参数配置和数据分析工具；
4. 完成实验并确认已经获得有效实验数据后：
   - 保存实验配置、脚本、汇总结果和说明文档；
   - 提交 commit；
   - push 当前实验分支到远程仓库；
5. 不要把实验专用修改合并回 `main`；
6. 当前实验完成并上传后，将本地项目切回 `gazebo-experiment-v1` 对应版本，为下一个实验重新创建独立分支；
7. 不要删除已经完成的实验分支，也不要移动或覆盖 `gazebo-experiment-v1` 标签；
8. 每个实验结束时记录：
   - 分支名；
   - 最终 commit SHA；
   - 实验配置；
   - 数据保存位置；
   - 运行命令；
   - 是否成功完成。

示例流程：

```bash
git switch -c exp/08-iapf gazebo-experiment-v1

# 完成实验相关修改和实验运行

git add .
git commit -m "Complete experiment 08 IAPF evaluation"
git push -u origin exp/08-iapf

git switch --detach gazebo-experiment-v1
```
执行时不要修改或覆盖已有实验数据。