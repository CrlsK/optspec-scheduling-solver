"""
QCentroid Test Runner — load input.json and call qcentroid.run(...).

Mirrors the runtime convention of the tenant's other solvers (see
CrlsK/classical-scheduling-solver/app.py). The platform invokes:

    python app.py /path/to/input.json
"""
import json
import sys


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.json"

    with open(input_file) as f:
        dic = json.load(f)

    extra_arguments = dic.get("extra_arguments", {})
    solver_params = dic.get("solver_params", {})

    import qcentroid
    result = qcentroid.run(dic["data"], solver_params, extra_arguments)

    print(json.dumps(result, indent=2, default=str))
