Intelligent Academic Compliance & Document Orchestration System
Project Description
It is an end-to-end automated platform designed to streamline the processes of ingestion, validation and auditing of university academic documents (Discipline Sheets and Study Plans).

The system uses OCR and Generative AI technologies to extract structured data from complex PDFs, performing cross-document consistency checks (e.g., credit and semester verification) and AI-based quality audits. It features a robust migration engine that converts legacy documentation into modern canonical templates, with Word export functionalities, significantly reducing manual administrative effort and ensuring institutional compliance.

Key Features
Automatic ingestion and processing of complex PDF documents.
Structured data extraction using Google Gemini and EasyOCR.
Consistency and integrity checks between different documents.
Quality audit based on artificial intelligence.
Engine for converting old documents into standardized formats.
Automated export to Microsoft Word (.docx) format.
Backend
Language: Python 3
Framework: FastAPI
Server: Uvicorn
Database: SQLite
Data Validation: Pydantic
Security: JWT (JSON Web Tokens), PBKDF2 hashing
Frontend
Library: React 19
Build Tool: Vite
Styling: CSS Modules
State Management: Modern Hooks API
AI and Document Processing
Generative AI: Google Gemini
OCR: EasyOCR
String Matching: RapidFuzz (Fuzzy Matching)
PDF Manipulation: PyMuPDF (fitz), pdfplumber, pypdf
Word Automation: python-docx
Installation
Backend
Navigate to the backend directory: cd backend
Create a virtual environment: python -m venv venv
Activate the virtual environment:
Windows: venv\Scripts\activate
Linux/macOS: source venv/bin/activate
Install dependencies: pip install -r requirements.txt
Frontend
Navigate to the frontend directory: cd frontend
Install packages: npm install
Start the application: npm run dev
Configuration
The system requires a Google Gemini API key configured in the environment variables. See the .env.example file for more details.
