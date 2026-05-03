"""
services/tools/anoxpepred/service.py
======================================
AnOxPePred 抗氧化肽预测微服务。

继承 BioToolService 模板，只需实现 load_model() 和 predict_impl()。

启动方式：
---------
uvicorn services.tools.anoxpepred.service:app --port 8001 --host 0.0.0.0

环境变量：
---------
MODEL_PATH     - 模型权重路径（默认: tools/AnOxPePred/anoxpepred_data/）
"""