""" app.py — Flask REST API. """
import os
import uuid
from flask import Flask, request, jsonify
from src.loader import FileLoader
from src.preprocessor import Preprocessor
from src.engine import AlgorithmEngine
from src.audit import AuditLogger
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
audit = AuditLogger()

reports_store: dict = {}

VALID_ALGORITHMS = {"cosine", "winnowing", "jaccard", "ast", "all"}

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({"status": "ok", "service": "plagcheck", "version": "1.0.0"})

@app.route("/api/algorithms", methods=["GET"])
def api_algorithms():
    return jsonify({"algorithms": sorted(VALID_ALGORITHMS)})

@app.route("/api/check", methods=["POST"])
def api_check():
    data = request.json or {}
    files = data.get("files", [])
    algorithm = data.get("algorithm", os.environ.get("DEFAULT_ALGORITHM", "cosine"))
    try:
        threshold = float(data.get("threshold", os.environ.get("DEFAULT_THRESHOLD", "0.70")))
    except (ValueError, TypeError):
        return jsonify({"error": "threshold must be a number between 0 and 1."}), 400

    if not files or not isinstance(files, list):
        audit.log("API_ERROR", payload={"error": "Invalid or missing files list"})
        return jsonify({"error": "Please provide a list of file paths."}), 400

    if algorithm not in VALID_ALGORITHMS:
        return jsonify({"error": f"Invalid algorithm '{algorithm}'. Choose from: {sorted(VALID_ALGORITHMS)}"}), 400
        
    scan_id = str(uuid.uuid4())
    audit.log("SCAN_START", payload={"scan_id": scan_id, "files": files, "algorithm": algorithm})
    
    loader = FileLoader()
    preprocessor = Preprocessor()
    file_data = {}
    errors = []
    
    for path in files:
        try:
            raw_text = loader.load(path)
            is_python = path.lower().endswith(".py")
            tokens, kgrams = preprocessor.process(raw_text, is_python=is_python)
            file_data[os.path.basename(path)] = {
                "raw": raw_text,
                "tokens": tokens,
                "kgrams": kgrams,
                "is_python": is_python
            }
        except Exception as e:
            errors.append({"file": path, "error": str(e)})
            audit.log("FILE_REJECTED", payload={"scan_id": scan_id, "file": path, "error": str(e)})

    if len(file_data) < 2:
        return jsonify({
            "scan_id": scan_id,
            "error": "Need at least 2 valid files to compare.",
            "file_errors": errors
        }), 400

    engine = AlgorithmEngine(algorithm=algorithm)
    matrix = engine.compute(file_data)
    
    flagged = matrix.get_flagged(threshold)
    
    reports_store[scan_id] = flagged
    
    audit.log("SCAN_COMPLETE", payload={"scan_id": scan_id, "flagged_count": len(flagged)})
    
    return jsonify({
        "scan_id": scan_id,
        "flagged": flagged,
        "errors": errors
    })

@app.route("/api/report/<scan_id>", methods=["GET"])
def api_report(scan_id):
    if scan_id in reports_store:
        return jsonify({"scan_id": scan_id, "flagged": reports_store[scan_id]})
    return jsonify({"error": "Report not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
