"""User Management csv_response."""

import csv
import io

def _csv_response(header, rows, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    csv_data = output.getvalue()
    output.close()
    from flask import Response
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
