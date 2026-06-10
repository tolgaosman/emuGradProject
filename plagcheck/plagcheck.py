""" plagcheck.py — CLI entry point. """
import argparse
import os
from dotenv import load_dotenv
from src.loader import FileLoader
from src.preprocessor import Preprocessor
from src.engine import AlgorithmEngine
from src.reporter import ReportGenerator
from src.audit import AuditLogger

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Plagiarism and File Similarity Detection System")
    parser.add_argument("--files", nargs="+", required=True, help="List of file paths to scan")
    parser.add_argument("--algorithm", choices=["cosine", "winnowing", "jaccard", "ast", "all"], 
                        default=os.environ.get("DEFAULT_ALGORITHM", "cosine"),
                        help="Similarity algorithm to use")
    parser.add_argument("--threshold", type=float, 
                        default=float(os.environ.get("DEFAULT_THRESHOLD", "0.70")),
                        help="Similarity threshold (0.01 - 0.99)")
    parser.add_argument("--output", type=str, default="output", help="Output directory for reports")
    parser.add_argument("--format", choices=["html", "csv", "both"], default="both", help="Report format")
    
    args = parser.parse_args()
    
    if not (0.01 <= args.threshold <= 0.99):
        print("Error: Threshold must be between 0.01 and 0.99")
        return
        
    audit = AuditLogger()
    audit.log("SCAN_START", payload={"files": args.files, "algorithm": args.algorithm})
    
    loader = FileLoader()
    preprocessor = Preprocessor()
    file_data = {}
    
    print(f"Loading {len(args.files)} files...")
    for path in args.files:
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
            print(f"Skipping {path}: {e}")
            audit.log("FILE_REJECTED", payload={"file": path, "error": str(e)})

    if len(file_data) < 2:
        print("Error: Need at least 2 valid files to compare.")
        return

    print(f"Computing similarities using '{args.algorithm}'...")
    engine = AlgorithmEngine(algorithm=args.algorithm)
    matrix = engine.compute(file_data)
    
    reporter = ReportGenerator()
    artifacts = reporter.generate(matrix, args.output, threshold=args.threshold)
    
    print(f"\nScan complete. Flagged pairs (>= {args.threshold}):")
    flagged = matrix.get_flagged(args.threshold)
    if not flagged:
        print("  None")
    else:
        for f in flagged:
            print(f"  {f['file_a']} <-> {f['file_b']} : {f['score']:.4f}")
            
    print(f"\nArtifacts generated in '{args.output}':")
    if args.format in ["csv", "both"]:
        print(f"  - {artifacts['csv']}")
    if args.format in ["html", "both"]:
        print(f"  - {artifacts['html']}")
    print(f"  - {artifacts['heatmap']}")
    
    audit.log("SCAN_COMPLETE", payload={"flagged_count": len(flagged)})

if __name__ == "__main__":
    main()
