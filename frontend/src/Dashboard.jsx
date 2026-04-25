import { useEffect, useRef, useState } from 'react';
import styles from './Dashboard.module.css';
import {
  comparePdfsVisual,
  fetchCompetencySubjects,
  fetchRecommendedCompetencies,
  validateFdAgainstPlanMaster,
} from './services/compareApi';

const UploadIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const LogoutIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

function getChangeLabel(type) {
  if (type === 'replace') return 'Modified';
  if (type === 'insert') return 'Inserted';
  if (type === 'delete') return 'Deleted';
  return 'Changed';
}

function getStatusClass(side, isMissing) {
  if (side === 'left') {
    return isMissing ? 'leftMissing' : 'noHighlight';
  }

  return 'noHighlight';
}

function getValidationCardClass(severity) {
  if (severity === 'eroare') return styles.severityError;
  if (severity === 'avertisment') return styles.severityWarning;
  return styles.severityOk;
}

function getSeverityLabel(severity) {
  if (severity === 'eroare') return 'EROARE';
  if (severity === 'avertisment') return 'AVERTISMENT';
  return 'OK';
}

function formatDetailValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function sanitizeLines(lines) {
  if (!Array.isArray(lines)) return [];
  return lines.filter((line) => typeof line === 'string' && line.trim().length > 0);
}

function splitWords(text) {
  if (!text || typeof text !== 'string') return [];
  return text.trim().split(/\s+/).filter(Boolean);
}

function normalizeForCompare(text) {
  if (!text || typeof text !== 'string') return '';
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '');
}

function canBeSplitIntoKnownTokens(token, knownSet) {
  if (!token || token.length < 6) return false;
  for (let splitAt = 3; splitAt <= token.length - 3; splitAt += 1) {
    const leftPart = token.slice(0, splitAt);
    const rightPart = token.slice(splitAt);
    if (knownSet.has(leftPart) && knownSet.has(rightPart)) {
      return true;
    }
  }
  return false;
}

function shouldSuppressDiffToken(tokenNorm, localLeftSet, globalLeftSet) {
  if (!tokenNorm) return true;
  if (localLeftSet.has(tokenNorm) || globalLeftSet.has(tokenNorm)) {
    return true;
  }
  if (canBeSplitIntoKnownTokens(tokenNorm, localLeftSet)) {
    return true;
  }
  if (canBeSplitIntoKnownTokens(tokenNorm, globalLeftSet)) {
    return true;
  }
  return false;
}

function buildRightDiffMask(leftNormTokens, rightNormTokens) {
  if (rightNormTokens.length === 0) return [];

  const counts = new Map();
  for (const token of leftNormTokens) {
    if (!token) continue;
    counts.set(token, (counts.get(token) || 0) + 1);
  }

  return rightNormTokens.map((token) => {
    if (!token) return false;
    const available = counts.get(token) || 0;
    if (available > 0) {
      counts.set(token, available - 1);
      return false;
    }
    return true;
  });
}

function buildRightTokenDiffByLine(leftLines, rightLines, globalLeftTokenSet) {
  const rightTokensByLine = rightLines.map(splitWords);
  const rightTokensFlat = rightTokensByLine.flat();
  const rightNormFlat = rightTokensFlat.map(normalizeForCompare);
  const leftNormFlat = leftLines.flatMap(splitWords).map(normalizeForCompare);
  const diffMask = buildRightDiffMask(leftNormFlat, rightNormFlat);
  const localLeftSet = new Set(leftNormFlat.filter(Boolean));

  let cursor = 0;
  return rightTokensByLine.map((tokens, lineIndex) => {
    const tokenDiffs = diffMask.slice(cursor, cursor + tokens.length);
    const normalizedTokens = rightTokensByLine[lineIndex].map(normalizeForCompare);
    const filteredTokenDiffs = tokenDiffs.map((isDiff, tokenIndex) => {
      if (!isDiff) return false;
      const tokenNorm = normalizedTokens[tokenIndex];
      return !shouldSuppressDiffToken(tokenNorm, localLeftSet, globalLeftTokenSet);
    });
    cursor += tokens.length;
    return { tokens, tokenDiffs: filteredTokenDiffs };
  });
}

function buildHighlightedSegments(tokens, tokenDiffs) {
  if (!tokens || tokens.length === 0) return [];

  const segments = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const text = tokens[index];
    const diff = Boolean(tokenDiffs?.[index]);
    const last = segments[segments.length - 1];
    if (last && last.diff === diff) {
      last.text = `${last.text} ${text}`;
    } else {
      segments.push({ text, diff });
    }
  }

  return segments;
}

function alignBlockRows(block, globalLeftTokenSet) {
  const leftLines = sanitizeLines(block.left_lines);
  const rightLines = sanitizeLines(block.right_lines);
  const rightTokenDiffByLine = buildRightTokenDiffByLine(leftLines, rightLines, globalLeftTokenSet);

  // Ignore invalid/empty diff blocks to avoid fake "[linie lipsa]" rows on both sides.
  if (leftLines.length === 0 && rightLines.length === 0) {
    return null;
  }

  const leftStart = (block.left_range?.start ?? 0) + 1;
  const rightStart = (block.right_range?.start ?? 0) + 1;
  const maxRows = Math.max(leftLines.length, rightLines.length);

  let leftCounter = 0;
  let rightCounter = 0;
  const rows = [];

  for (let index = 0; index < maxRows; index += 1) {
    const hasLeft = index < leftLines.length;
    const hasRight = index < rightLines.length;

    const leftText = hasLeft ? leftLines[index] : '';
    const rightText = hasRight ? rightLines[index] : '';
    const rightTokenInfo = hasRight ? rightTokenDiffByLine[index] : { tokens: [], tokenDiffs: [] };

    rows.push({
      left: {
        text: leftText,
        lineNumber: hasLeft ? leftStart + leftCounter : '',
        missing: !hasLeft,
      },
      right: {
        text: rightText,
        lineNumber: hasRight ? rightStart + rightCounter : '',
        missing: !hasRight,
        tokens: rightTokenInfo.tokens,
        tokenDiffs: rightTokenInfo.tokenDiffs,
      },
    });

    if (hasLeft) leftCounter += 1;
    if (hasRight) rightCounter += 1;
  }

  return {
    ...block,
    rows,
  };
}

function MetricCard({ label, value }) {
  return (
    <div className={styles.metricCard}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{value}</span>
    </div>
  );
}

function VersionBText({ rightLine }) {
  const segments = buildHighlightedSegments(rightLine?.tokens, rightLine?.tokenDiffs);
  if (segments.length === 0) return null;

  return (
    <>
      {segments.map((segment, index) => (
        <span
          key={`${segment.diff ? 'd' : 's'}-${index}`}
          className={segment.diff ? styles.bTokenDiff : undefined}
        >
          {segment.text}
          {index < segments.length - 1 ? ' ' : ''}
        </span>
      ))}
    </>
  );
}

export default function Dashboard({ onLogout }) {
  const [fdFileA, setFdFileA] = useState(null);
  const [fdFileB, setFdFileB] = useState(null);
  const [piFile, setPiFile] = useState(null);
  const [viewMode, setViewMode] = useState('upload');
  const [comparisonResult, setComparisonResult] = useState(null);
  const [validationResult, setValidationResult] = useState(null);
  const [resultTab, setResultTab] = useState('visual');
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState(null);
  const [error, setError] = useState('');
  const [competenceSubjects, setCompetenceSubjects] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState('');
  const [selectedCompetencies, setSelectedCompetencies] = useState([]);
  const [competenceLookupMessage, setCompetenceLookupMessage] = useState('');
  const [competenceLoading, setCompetenceLoading] = useState(false);

  const fdAInputRef = useRef(null);
  const fdBInputRef = useRef(null);
  const piInputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const loadCompetencySubjects = async () => {
      try {
        const subjects = await fetchCompetencySubjects();
        if (cancelled) return;
        setCompetenceSubjects(subjects);
        if (subjects.length === 0) {
          setCompetenceLookupMessage('Nu exista materii disponibile momentan.');
        }
      } catch (err) {
        if (cancelled) return;
        setCompetenceLookupMessage(err.message || 'Nu am putut incarca lista de materii.');
      }
    };

    loadCompetencySubjects();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleFileChange = (event, type) => {
    const file = event.target.files[0];
    if (!file) return;

    if (type === 'fdA') setFdFileA(file);
    if (type === 'fdB') setFdFileB(file);
    if (type === 'pi') setPiFile(file);
  };

  const handleStartAnalysis = async () => {
    if (!fdFileA || !fdFileB) {
      setError('Select PDF A and PDF B before running comparison.');
      return;
    }

    setLoading(true);
    setActiveAction('visual');
    setError('');

    try {
      const response = await comparePdfsVisual(fdFileA, fdFileB);
      setComparisonResult(response);
      setResultTab('visual');
      setViewMode('results');
    } catch (err) {
      setError(err.message || 'Comparison failed. Try again.');
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const handleRunPlanValidation = async () => {
    if (!fdFileA || !piFile) {
      setError('Select PDF Version A and Plan Master before validating.');
      return;
    }

    setLoading(true);
    setActiveAction('validation');
    setError('');

    try {
      const response = await validateFdAgainstPlanMaster(fdFileA, piFile);
      setValidationResult(response);
      setResultTab('validation');
      setViewMode('results');
    } catch (err) {
      setError(err.message || 'Validation failed. Try again.');
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const changes = comparisonResult?.changes || [];
  const globalLeftTokenSet = new Set(
    changes
      .flatMap((block) => sanitizeLines(block.left_lines))
      .flatMap(splitWords)
      .map(normalizeForCompare)
      .filter(Boolean),
  );
  const alignedChanges = changes.map((block) => alignBlockRows(block, globalLeftTokenSet)).filter(Boolean);
  const summary = comparisonResult?.summary;
  const validationSummary = validationResult?.sumar;
  const validationRows = Array.isArray(validationResult?.rezultate) ? validationResult.rezultate : [];
  const subjectOptions = competenceSubjects;
  const resultTitle = resultTab === 'validation' ? 'FD vs Plan Master Differences' : 'Side-by-Side Visual Comparison';

  const handleShowSubjectCompetencies = async () => {
    if (!selectedSubject) {
      setSelectedCompetencies([]);
      setCompetenceLookupMessage('Selecteaza o materie pentru a afisa competentele.');
      return;
    }

    setCompetenceLoading(true);
    try {
      const response = await fetchRecommendedCompetencies(selectedSubject);
      const competencies = response?.competencies || [];
      setSelectedCompetencies(competencies);

      if (competencies.length === 0) {
        setCompetenceLookupMessage(`Nu exista competente recomandate pentru materia "${selectedSubject}".`);
      } else {
        setCompetenceLookupMessage(`Competente recomandate pentru "${selectedSubject}" (${competencies.length}).`);
      }
    } catch (err) {
      setSelectedCompetencies([]);
      setCompetenceLookupMessage(err.message || 'Nu am putut obtine competentele pentru materia selectata.');
    } finally {
      setCompetenceLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.logo}>DocManage AI</div>
        <button className={styles.logoutButton} onClick={onLogout}>
          <LogoutIcon /> <span>Logout</span>
        </button>
      </header>

      <main className={styles.main}>
        {viewMode === 'upload' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Upload PDFs for Visual Comparison</h1>

            {error && <div className={styles.errorBox}>{error}</div>}

            <div className={styles.uploadCardsContainer}>
              <div className={`${styles.uploadCard} ${fdFileA ? styles.fileSelected : ''}`} onClick={() => fdAInputRef.current.click()}>
                <div className={styles.uploadIcon}>{fdFileA ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>PDF Version A</h3>
                <p>{fdFileA ? fdFileA.name : 'Upload first document'}</p>
                <input
                  ref={fdAInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'fdA')}
                />
              </div>

              <div className={`${styles.uploadCard} ${fdFileB ? styles.fileSelected : ''}`} onClick={() => fdBInputRef.current.click()}>
                <div className={styles.uploadIcon}>{fdFileB ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>PDF Version B</h3>
                <p>{fdFileB ? fdFileB.name : 'Upload second document'}</p>
                <input
                  ref={fdBInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'fdB')}
                />
              </div>

              <div className={`${styles.uploadCard} ${piFile ? styles.fileSelected : ''}`} onClick={() => piInputRef.current.click()}>
                <div className={styles.uploadIcon}>{piFile ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>Master Plan (optional)</h3>
                <p>{piFile ? piFile.name : 'Optional field (kept in UI)'}</p>
                <input
                  ref={piInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'pi')}
                />
              </div>
            </div>

            <p className={styles.infoText}>
              Use the first button for visual compare (PDF A vs PDF B). Use the second button for
              FD corelation against Plan Master (PDF A vs Plan Master).
            </p>

            <section className={styles.competenceFinderCard}>
              <h3 className={styles.competenceFinderTitle}>Recomandare competente pe materie</h3>
              <div className={styles.competenceFinderControls}>
                <select
                  className={styles.subjectSelect}
                  value={selectedSubject}
                  onChange={(event) => {
                    setSelectedSubject(event.target.value);
                    setSelectedCompetencies([]);
                    setCompetenceLookupMessage('');
                  }}
                  disabled={subjectOptions.length === 0}
                >
                  <option value="">Selecteaza o materie</option>
                  {subjectOptions.map((subject) => (
                    <option key={subject} value={subject}>{subject}</option>
                  ))}
                </select>
                <button
                  className={styles.findCompetenceButton}
                  onClick={handleShowSubjectCompetencies}
                  disabled={subjectOptions.length === 0 || !selectedSubject || competenceLoading}
                >
                  {competenceLoading ? 'Se cauta...' : 'Arata competente'}
                </button>
              </div>
              {competenceLookupMessage ? (
                <p className={styles.competenceLookupMessage}>{competenceLookupMessage}</p>
              ) : null}
              {selectedCompetencies.length > 0 ? (
                <div className={styles.competenceWrap}>
                  {selectedCompetencies.map((itemCompetence, competenceIndex) => (
                    <span key={`selected-comp-${competenceIndex}`} className={styles.competenceTag}>
                      {itemCompetence}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>

            <div className={styles.buttonRow}>
              <button className={styles.analyzeButton} onClick={handleStartAnalysis} disabled={!fdFileA || !fdFileB || loading}>
                {loading && activeAction === 'visual' ? 'Processing...' : 'Run Visual Comparison'}
              </button>
              <button
                className={styles.secondaryButton}
                onClick={handleRunPlanValidation}
                disabled={!fdFileA || !piFile || loading}
              >
                {loading && activeAction === 'validation' ? 'Processing...' : 'Show FD vs Plan Differences'}
              </button>
            </div>
          </section>
        ) : (
          <div className={styles.diffContainer}>
            <div className={styles.diffHeader}>
              <button className={styles.backButton} onClick={() => setViewMode('upload')}>
                Back to Upload
              </button>
              <h2>{resultTitle}</h2>
              {resultTab === 'visual' && comparisonResult?.html_report_url ? (
                <a className={styles.reportButton} href={comparisonResult.html_report_url} target="_blank" rel="noreferrer">
                  Open HTML Report
                </a>
              ) : (
                <span />
              )}
            </div>

            <div className={styles.resultSwitch}>
              <button
                className={`${styles.switchButton} ${resultTab === 'visual' ? styles.switchButtonActive : ''}`}
                onClick={() => setResultTab('visual')}
                disabled={!comparisonResult}
              >
                Visual Compare
              </button>
              <button
                className={`${styles.switchButton} ${resultTab === 'validation' ? styles.switchButtonActive : ''}`}
                onClick={() => setResultTab('validation')}
                disabled={!validationResult}
              >
                FD vs Plan Master
              </button>
            </div>

            {resultTab === 'visual' && (
              <>
                {summary && (
                  <div className={styles.metricGrid}>
                    <MetricCard label="Similarity" value={`${(summary.similarity_ratio * 100).toFixed(2)}%`} />
                    <MetricCard label="Equal" value={summary.equal_lines} />
                    <MetricCard label="Modified" value={summary.replaced_lines} />
                    <MetricCard label="A-only" value={summary.deleted_lines} />
                    <MetricCard label="B-only" value={summary.inserted_lines} />
                  </div>
                )}

                <div className={styles.diffWrapper}>
                  <div className={styles.diffColumn}>
                    <div className={styles.columnLabel}>VERSION A (REFERINTA)</div>
                    <div className={styles.lineArea}>
                      {alignedChanges.length === 0 ? (
                        <div className={styles.emptyState}>No differences found.</div>
                      ) : (
                        alignedChanges.map((block, blockIndex) => (
                          <div key={`left-${blockIndex}`} className={styles.changeBlock}>
                            <div className={styles.blockTitle}>{getChangeLabel(block.type)}</div>
                            {block.rows.map((row, rowIndex) => {
                              const leftClassName = styles[getStatusClass('left', row.left.missing)];
                              return (
                                <div key={`left-line-${blockIndex}-${rowIndex}`} className={`${styles.diffLine} ${leftClassName}`}>
                                  <span className={styles.lineNum}>{row.left.lineNumber}</span>
                                  <span className={styles.lineText}>{row.left.text}</span>
                                </div>
                              );
                            })}
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div className={styles.diffColumn}>
                    <div className={styles.columnLabel}>VERSION B (COMPARAT)</div>
                    <div className={styles.lineArea}>
                      {alignedChanges.length === 0 ? (
                        <div className={styles.emptyState}>No differences found.</div>
                      ) : (
                        alignedChanges.map((block, blockIndex) => (
                          <div key={`right-${blockIndex}`} className={styles.changeBlock}>
                            <div className={styles.blockTitle}>{getChangeLabel(block.type)}</div>
                            {block.rows.map((row, rowIndex) => {
                              const rightClassName = styles[getStatusClass('right', row.right.missing)];
                              return (
                                <div key={`right-line-${blockIndex}-${rowIndex}`} className={`${styles.diffLine} ${rightClassName}`}>
                                  <span className={styles.lineNum}>{row.right.lineNumber}</span>
                                  <span className={styles.lineText}>
                                    <VersionBText rightLine={row.right} />
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {resultTab === 'validation' && (
              <div className={styles.validationContainer}>
                {validationSummary ? (
                  <div className={styles.metricGrid}>
                    <MetricCard label="Total FD" value={validationSummary.total_fise} />
                    <MetricCard label="Total Plan" value={validationSummary.total_discipline_plan} />
                    <MetricCard label="Erori" value={validationSummary.erori} />
                    <MetricCard label="Avertismente" value={validationSummary.avertismente} />
                    <MetricCard label="OK" value={validationSummary.ok} />
                  </div>
                ) : null}

                <div className={styles.validationSourceRow}>
                  <span>Sursa plan: {validationResult?.sursa_plan || '-'}</span>
                  <span>Discipline extrase PI: {validationResult?.plan_extras ?? '-'}</span>
                </div>

                {validationRows.length === 0 ? (
                  <div className={styles.emptyState}>No validation results yet.</div>
                ) : (
                  <div className={styles.validationList}>
                    {validationRows.map((item, index) => {
                      const details = Object.entries(item?.detalii || {});
                      const competencies = Array.isArray(item?.competente_recomandate) ? item.competente_recomandate : [];

                      return (
                        <article key={`validation-${index}`} className={`${styles.validationCard} ${getValidationCardClass(item?.severitate)}`}>
                          <div className={styles.validationTopRow}>
                            <span className={styles.validationBadge}>{getSeverityLabel(item?.severitate)}</span>
                            <span className={styles.validationType}>{item?.tip || 'tip_necunoscut'}</span>
                          </div>

                          <h3 className={styles.validationTitle}>{item?.nume_fisa || 'Disciplina'}</h3>
                          <p className={styles.validationMessage}>{item?.mesaj || '-'}</p>

                          <div className={styles.validationMetaRow}>
                            <span>Cod FD: {item?.cod_fisa || '-'}</span>
                            <span>Semestru FD: {item?.semestru_fisa ?? '-'}</span>
                          </div>

                          {details.length > 0 ? (
                            <div className={styles.detailGrid}>
                              {details.map(([key, value]) => (
                                <div key={`${index}-${key}`} className={styles.detailItem}>
                                  <span className={styles.detailKey}>{key}</span>
                                  <span className={styles.detailValue}>{formatDetailValue(value)}</span>
                                </div>
                              ))}
                            </div>
                          ) : null}

                          {competencies.length > 0 ? (
                            <div className={styles.competenceWrap}>
                              {competencies.map((itemCompetence, competenceIndex) => (
                                <span key={`${index}-comp-${competenceIndex}`} className={styles.competenceTag}>
                                  {itemCompetence}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
