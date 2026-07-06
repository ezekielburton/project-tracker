from app.pptx_convert import convert_pptx_to_pdf

with open(r'C:\temp\test.pptx', 'rb') as f:
    pdf_bytes = convert_pptx_to_pdf(f.read())

with open(r'C:\temp\output.pdf', 'wb') as f:
    f.write(pdf_bytes)