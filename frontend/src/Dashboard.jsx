import React, { useState, useRef } from 'react';
import styles from './Dashboard.module.css';

// Icons
const UploadIcon = () => ( <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg> );
const CheckCircleIcon = () => ( <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg> );
const LogoutIcon = () => ( <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg> );

export default function Dashboard({ onLogout }) {
  const [fdFileA, setFdFileA] = useState(null);
  const [fdFileB, setFdFileB] = useState(null);
  const [piFile, setPiFile] = useState(null);
  const [viewMode, setViewMode] = useState('upload'); 
  const [comparisonResult, setComparisonResult] = useState(null); 
  const [loading, setLoading] = useState(false);

  const fdAInputRef = useRef(null);
  const fdBInputRef = useRef(null);
  const piInputRef = useRef(null);

  const handleFileChange = (e, type) => {
    const file = e.target.files[0];
    if (file) {
      if (type === 'fdA') setFdFileA(file);
      else if (type === 'fdB') setFdFileB(file);
      else if (type === 'pi') setPiFile(file);
    }
  };

  // FUNCTIA MODIFICATA PENTRU SIMULARE (FĂRĂ SERVER)
  const handleStartAnalysis = () => {
    if (!fdFileA || !fdFileB || !piFile) return;

    setLoading(true);

    // Simulăm un timp de așteptare de 1.5 secunde (ca să pară că serverul lucrează)
    setTimeout(() => {
      // PUNEM DATELE DIN JSON-UL TĂU AICI
      const mockResponse = {
        "summary": {
          "left_line_count": 195,
          "right_line_count": 4519,
          "similarity_ratio": 0.0042
        },
        "changes": [
          {
            "type": "replace",
            "left_lines": [
              "PLAN DE INVATAMANT",
              "al promotiei 2023 - 2026",
              "Universitatea Transilvania din Brasov"
            ],
            "right_lines": [
              "FIŞA DISCIPLINEI",
              "F03.1-PS7.2-01/ed.3, rev.6",
              "1. Date despre program"
            ]
          },
          {
            "type": "replace",
            "left_lines": [
              "1. OBIECTIVE DE FORMARE §i COMPETENTE",
              "Obiectivul general al programului"
            ],
            "right_lines": [
              "6. Competențe specifice acumulate",
              "CP 4 Utilizarea bazelor teoretice"
            ]
          }
          // Poți adăuga mai multe blocuri aici dacă vrei
        ]
      };

      setComparisonResult(mockResponse);
      setViewMode('results');
      setLoading(false);
    }, 1500);
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.logo}>📚 DocManage AI</div>
        <button className={styles.logoutButton} onClick={onLogout}>
          <LogoutIcon /> <span>Logout</span>
        </button>
      </header>

      <main className={styles.main}>
        {viewMode === 'upload' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Step 1: Upload Documents for Comparison</h1>
            <div className={styles.uploadCardsContainer}>
              <div className={`${styles.uploadCard} ${fdFileA ? styles.fileSelected : ''}`} onClick={() => fdAInputRef.current.click()}>
                <div className={styles.uploadIcon}>{fdFileA ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>Syllabus Version A</h3>
                <p>{fdFileA ? fdFileA.name : 'Old Version'}</p>
                <input ref={fdAInputRef} type="file" className={styles.hiddenInput} onChange={(e) => handleFileChange(e, 'fdA')} />
              </div>
              <div className={`${styles.uploadCard} ${fdFileB ? styles.fileSelected : ''}`} onClick={() => fdBInputRef.current.click()}>
                <div className={styles.uploadIcon}>{fdFileB ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>Syllabus Version B</h3>
                <p>{fdFileB ? fdFileB.name : 'New Version'}</p>
                <input ref={fdBInputRef} type="file" className={styles.hiddenInput} onChange={(e) => handleFileChange(e, 'fdB')} />
              </div>
              <div className={`${styles.uploadCard} ${piFile ? styles.fileSelected : ''}`} onClick={() => piInputRef.current.click()}>
                <div className={styles.uploadIcon}>{piFile ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>Master Plan (PI)</h3>
                <p>{piFile ? piFile.name : 'Plan de Invățământ'}</p>
                <input ref={piInputRef} type="file" className={styles.hiddenInput} onChange={(e) => handleFileChange(e, 'pi')} />
              </div>
            </div>
            <div style={{display: 'flex', justifyContent: 'center', marginTop: '3rem'}}>
              <button 
                className={styles.analyzeButton} 
                onClick={handleStartAnalysis} 
                disabled={!fdFileA || !fdFileB || !piFile || loading}
              >
                {loading ? 'Processing...' : '🚀 Run Visual Comparison'}
              </button>
            </div>
          </section>
        ) : (
          <div className={styles.diffContainer}>
            <div className={styles.diffHeader}>
              <button className={styles.backButton} onClick={() => setViewMode('upload')}>← Back to Upload</button>
              <h2>Side-by-Side Visual Comparison</h2>
              {comparisonResult && (
                <div style={{fontSize: '0.9rem', color: '#64748b'}}>
                  Similarity Ratio: {(comparisonResult.summary.similarity_ratio * 100).toFixed(2)}%
                </div>
              )}
            </div>

            <div className={styles.diffWrapper}>
              {/* COLOANA STÂNGA */}
              <div className={styles.diffColumn}>
                <div className={styles.columnLabel}>VERSION A (OLD)</div>
                <div className={styles.lineArea}>
                  {comparisonResult && comparisonResult.changes.map((block, bIdx) => (
                    <div key={`block-l-${bIdx}`} className={styles.changeBlock}>
                      {block.left_lines.map((line, lIdx) => (
                        <div key={`l-${lIdx}`} className={`${styles.diffLine} ${styles.removed}`}>
                          <span className={styles.lineNum}>{lIdx + 1}</span>
                          <span className={styles.lineText}>{line}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>

              {/* COLOANA DREAPTĂ */}
              <div className={styles.diffColumn}>
                <div className={styles.columnLabel}>VERSION B (NEW)</div>
                <div className={styles.lineArea}>
                  {comparisonResult && comparisonResult.changes.map((block, bIdx) => (
                    <div key={`block-r-${bIdx}`} className={styles.changeBlock}>
                      {block.right_lines.map((line, rIdx) => (
                        <div key={`r-${rIdx}`} className={`${styles.diffLine} ${styles.added}`}>
                          <span className={styles.lineNum}>{rIdx + 1}</span>
                          <span className={styles.lineText}>{line}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}