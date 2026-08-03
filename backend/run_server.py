import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
log = open(r"D:\AIhumannew\server_log.txt", "w", encoding="utf-8")
try:
    log.write("Starting server...\n"); log.flush()
    from flask import Flask, request, jsonify, send_from_directory
    from flask_cors import CORS
    log.write("Flask imports OK\n"); log.flush()
    from knowledge_base import get_knowledge_base, init_knowledge_base
    log.write("KB import OK\n"); log.flush()
    from rag_service import RAGService
    log.write("RAG import OK\n"); log.flush()

    app = Flask(__name__, static_folder=r"D:\AIhumannew\frontend")
    CORS(app)
    docs_path = r"D:\AIhumannew\20260323113204906\示范景区公开资料包"
    log.write(f"Docs path: {docs_path}\n"); log.flush()
    init_knowledge_base(docs_path)
    log.write("KB loaded\n"); log.flush()
    rag = RAGService()
    log.write("RAG initialized\n"); log.flush()

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json()
        if not data: return jsonify({"answer": "nodata"})
        query = data.get("query", "").strip()
        if not query: return jsonify({"answer": "noquery"})
        answer = rag.chat(query, data.get("history"))
        return jsonify({"answer": answer})

    @app.route("/api/routes")
    def get_routes():
        return jsonify({"routes": get_knowledge_base().get_tour_routes()})

    log.write("Starting Flask on :8000\n"); log.flush()
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
except Exception as e:
    log.write(f"FATAL: {e}\n{traceback.format_exc()}\n")
    log.flush()
finally:
    log.close()
