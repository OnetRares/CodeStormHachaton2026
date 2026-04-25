import { useEffect, useRef, useState } from 'react';
import styles from './Dashboard.module.css';
import { batchUpdate } from './services/batchUpdateApi';
import {
  comparePdfsVisual,
  fetchCompetencySubjects,
  fetchWeightsHoursCheck,
  fetchRecommendedCompetencies,
  migrateFdToTemplate,
  prefillSingleFdTemplateFromPi,
  validateSingleFdPdf,
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

function getCheckStatusLabel(status) {
  if (status === 'ok') return 'OK';
  if (status === 'missing') return 'MISSING';
  return 'NOT OK';
}

function getCheckStatusClass(status) {
  if (status === 'ok') return styles.smallBadgeOk;
  if (status === 'missing') return styles.smallBadgeMissing;
  return styles.smallBadgeBad;
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
  const [fdSingleFile, setFdSingleFile] = useState(null);
  const [fdPrefillFile, setFdPrefillFile] = useState(null);
  const [fdMigrationFile, setFdMigrationFile] = useState(null);
  const [viewMode, setViewMode] = useState('upload'); // 'upload', 'results', 'batch', 'quality', 'fdsingle', 'fdprefill', 'fdmigrate'
  const [comparisonResult, setComparisonResult] = useState(null);
  const [validationResult, setValidationResult] = useState(null);
  const [singleFdValidationResult, setSingleFdValidationResult] = useState(null);
  const [singleFdPrefillResult, setSingleFdPrefillResult] = useState(null);
  const [singleFdMigrationResult, setSingleFdMigrationResult] = useState(null);
  const [resultTab, setResultTab] = useState('visual');
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState(null);
  const [error, setError] = useState('');
  const [competenceSubjects, setCompetenceSubjects] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState('');
  const [selectedCompetencies, setSelectedCompetencies] = useState([]);
  const [competenceLookupMessage, setCompetenceLookupMessage] = useState('');
  const [competenceLoading, setCompetenceLoading] = useState(false);

  // Batch update states
  const [oldText, setOldText] = useState('');
  const [newText, setNewText] = useState('');
  const [batchResults, setBatchResults] = useState(null);
  const [targetJsonFile, setTargetJsonFile] = useState('fisa_disciplina_out.json');
  const [selectedBatchFile, setSelectedBatchFile] = useState('');
  const [weightsHoursResult, setWeightsHoursResult] = useState(null);
  const [weightsHoursDbPath, setWeightsHoursDbPath] = useState('data/discipline_new.db');
  const [weightsHoursFilter, setWeightsHoursFilter] = useState('all');

  const fdAInputRef = useRef(null);
  const fdBInputRef = useRef(null);
  const piInputRef = useRef(null);
  const fdSingleInputRef = useRef(null);
  const fdPrefillInputRef = useRef(null);
  const fdMigrationInputRef = useRef(null);

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
    if (type === 'fdSingle') {
      setFdSingleFile(file);
      setSingleFdValidationResult(null);
    }
    if (type === 'fdPrefill') {
      setFdPrefillFile(file);
      setSingleFdPrefillResult(null);
    }
    if (type === 'fdMigration') {
      setFdMigrationFile(file);
      setSingleFdMigrationResult(null);
    }
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

  const handleBatchUpdate = async () => {
    if (!oldText.trim()) {
      setError('Te rugam sa introduci textul de cautat.');
      return;
    }

    setLoading(true);
    setError('');
    setBatchResults(null);

    try {
      const response = await batchUpdate(oldText, newText, {
        targetJsonFile: targetJsonFile.trim() || undefined,
      });
      setBatchResults(response.results);
      const firstFile = response?.results?.file_details?.[0]?.file || '';
      setSelectedBatchFile(firstFile);
    } catch (err) {
      setError(err.message || 'Actualizarea in masa a esuat.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunWeightsHoursCheck = async () => {
    setLoading(true);
    setActiveAction('weights-hours');
    setError('');
    setWeightsHoursResult(null);

    try {
      const response = await fetchWeightsHoursCheck(weightsHoursDbPath);
      setWeightsHoursResult(response);
      setWeightsHoursFilter('all');
    } catch (err) {
      setError(err.message || 'Nu am putut rula verificarea de ponderi si ore.');
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const handleRunSingleFdValidation = async () => {
    if (!fdSingleFile) {
      setError('Selecteaza un PDF pentru validare.');
      return;
    }

    setLoading(true);
    setActiveAction('fd-single');
    setError('');
    setSingleFdValidationResult(null);

    try {
      const response = await validateSingleFdPdf(fdSingleFile);
      setSingleFdValidationResult(response);
    } catch (err) {
      setError(err.message || 'Validarea fisei a esuat.');
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const handleRunSingleFdPrefill = async () => {
    if (!fdPrefillFile) {
      setError('Selecteaza un PDF pentru precompletare.');
      return;
    }

    setLoading(true);
    setActiveAction('fd-prefill');
    setError('');
    setSingleFdPrefillResult(null);

    try {
      const response = await prefillSingleFdTemplateFromPi(fdPrefillFile);
      setSingleFdPrefillResult(response);
    } catch (err) {
      setError(err.message || 'Precompletarea fisei a esuat.');
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const handleRunSingleFdMigration = async () => {
    if (!fdMigrationFile) {
      setError('Selecteaza un PDF pentru migrare.');
      return;
    }

    setLoading(true);
    setActiveAction('fd-migrate');
    setError('');
    setSingleFdMigrationResult(null);

    try {
      const response = await migrateFdToTemplate(fdMigrationFile);
      setSingleFdMigrationResult(response);
    } catch (err) {
      setError(err.message || 'Migrarea catre noul template a esuat.');
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
  const batchFileDetails = Array.isArray(batchResults?.file_details) ? batchResults.file_details : [];
  const selectedBatchDetail = batchFileDetails.find((item) => item.file === selectedBatchFile) || batchFileDetails[0] || null;
  const selectedSentenceExamples = Array.isArray(selectedBatchDetail?.sentence_examples)
    ? selectedBatchDetail.sentence_examples
    : [];
  const weightsSummary = weightsHoursResult?.summary || null;
  const weightsRows = Array.isArray(weightsHoursResult?.rows) ? weightsHoursResult.rows : [];
  const filteredWeightsRows = weightsRows.filter((row) => {
    if (weightsHoursFilter === 'ok') return row?.overall_status === 'ok';
    if (weightsHoursFilter === 'not_ok') return row?.overall_status !== 'ok';
    return true;
  });
  const fdSingleMissing = Array.isArray(singleFdValidationResult?.missing_fields)
    ? singleFdValidationResult.missing_fields
    : [];
  const fdSingleMathErrors =
    singleFdValidationResult?.math_errors && typeof singleFdValidationResult.math_errors === 'object'
      ? Object.entries(singleFdValidationResult.math_errors)
      : [];
  const fdSingleCanonical = singleFdValidationResult?.fisa_canonical || null;
  const fdPrefillMatchedDiscipline = singleFdPrefillResult?.matched_discipline || '-';
  const fdMigrationMatchedDiscipline = singleFdMigrationResult?.disciplina || '-';
  const fdMigrationMissingRequired = Array.isArray(singleFdMigrationResult?.required_fields_missing)
    ? singleFdMigrationResult.required_fields_missing
    : [];
  const fdMigrationCoveragePercent = Number(singleFdMigrationResult?.coverage_required ?? 0) * 100;
  const fdMigrationTemplatePreview = singleFdMigrationResult?.template_preview || null;
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
        <div className={styles.navGroup}>
          <button 
            className={`${styles.navButton} ${viewMode === 'upload' || viewMode === 'results' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('upload')}
          >
            Visual Comparison
          </button>
          <button 
            className={`${styles.navButton} ${viewMode === 'batch' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('batch')}
          >
            Batch Update
          </button>
          <button
            className={`${styles.navButton} ${viewMode === 'quality' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('quality')}
          >
            Weights & Hours
          </button>
          <button
            className={`${styles.navButton} ${viewMode === 'fdsingle' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('fdsingle')}
          >
            FD Validator
          </button>
          <button
            className={`${styles.navButton} ${viewMode === 'fdprefill' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('fdprefill')}
          >
            FD Prefill
          </button>
          <button
            className={`${styles.navButton} ${viewMode === 'fdmigrate' ? styles.activeNav : ''}`}
            onClick={() => setViewMode('fdmigrate')}
          >
            FD Migrare
          </button>
        </div>
        <button className={styles.logoutButton} onClick={onLogout}>
          <LogoutIcon /> <span>Logout</span>
        </button>
      </header>

      <main className={styles.main}>
        {viewMode === 'batch' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Global Batch Update</h1>
            <p className={styles.infoText}>
              Aceasta functie iti permite sa modifici un text in toate fisierele si planurile simultan.
              De exemplu, poti schimba un nume de disciplina peste tot.
            </p>

            {error && <div className={styles.errorBox}>{error}</div>}
            {batchResults && (
              <div className={styles.successBox}>
                <h3>Actualizare reusita!</h3>
                <ul>
                  <li>Fisiere actualizate: {batchResults.files_updated}</li>
                  <li>Total modificari: {batchResults.total_matches}</li>
                </ul>
              </div>
            )}

            <div className={styles.batchForm}>
              <div className={styles.inputGroup}>
                <label>Text de cautat (vechi)</label>
                <input 
                  type="text" 
                  value={oldText} 
                  onChange={(e) => setOldText(e.target.value)}
                  placeholder="Ex: Analiza"
                  className={styles.textInput}
                />
              </div>
              <div className={styles.inputGroup}>
                <label>Text nou</label>
                <input 
                  type="text" 
                  value={newText} 
                  onChange={(e) => setNewText(e.target.value)}
                  placeholder="Ex: Analiza 6"
                  className={styles.textInput}
                />
              </div>
              <div className={styles.inputGroup}>
                <label>Fisier JSON tinta (optional)</label>
                <input
                  type="text"
                  value={targetJsonFile}
                  onChange={(e) => setTargetJsonFile(e.target.value)}
                  placeholder="Ex: fisa_disciplina_out.json"
                  className={styles.textInput}
                />
              </div>
              <div className={styles.buttonRow}>
                <button 
                  className={styles.analyzeButton} 
                  onClick={handleBatchUpdate} 
                  disabled={loading || !oldText.trim()}
                >
                  {loading ? 'Se actualizeaza...' : 'Aplica modificarile in masa'}
                </button>
              </div>
            </div>

            {batchResults && (
              <section className={styles.batchSentencePanel}>
                <div className={styles.batchSentenceHeader}>
                  <h3>Propozitii modificate</h3>
                  {batchFileDetails.length > 1 ? (
                    <select
                      className={styles.subjectSelect}
                      value={selectedBatchDetail?.file || ''}
                      onChange={(event) => setSelectedBatchFile(event.target.value)}
                    >
                      {batchFileDetails.map((detail) => (
                        <option key={detail.file} value={detail.file}>
                          {detail.file}
                        </option>
                      ))}
                    </select>
                  ) : null}
                </div>

                {selectedBatchDetail ? (
                  <p className={styles.batchSentenceSummary}>
                    Fisier: <strong>{selectedBatchDetail.file}</strong> | Inlocuiri: <strong>{selectedBatchDetail.matches}</strong> | Propozitii gasite: <strong>{selectedSentenceExamples.length}</strong>
                  </p>
                ) : null}

                {selectedSentenceExamples.length === 0 ? (
                  <div className={styles.emptyState}>Nu exista propozitii modificate pentru selectia curenta.</div>
                ) : (
                  <div className={styles.batchSentenceList}>
                    {selectedSentenceExamples.map((entry, index) => (
                      <article key={`${entry.file}-${entry.page ?? 'no-page'}-${index}`} className={styles.batchSentenceCard}>
                        <div className={styles.batchSentenceMeta}>
                          <span>#{index + 1}</span>
                          <span>Pagina: {entry.page ?? '-'}</span>
                          <span>Aparitii: {entry.occurrences ?? 1}</span>
                        </div>
                        <div className={styles.batchSentenceTextWrap}>
                          <p className={styles.batchSentenceBefore}>
                            <strong>Inainte:</strong> {entry.before}
                          </p>
                          <p className={styles.batchSentenceAfter}>
                            <strong>Dupa:</strong> {entry.after}
                          </p>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}
          </section>
        ) : viewMode === 'quality' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Weights & Hours Integrity Check</h1>
            <p className={styles.infoText}>
              Verifica daca orele sunt corecte (ore_saptamana * 14 = total_ore_plan)
              si daca suma ponderilor este 100 pentru fiecare disciplina.
            </p>

            {error && <div className={styles.errorBox}>{error}</div>}

            <div className={styles.batchForm}>
              <div className={styles.inputGroup}>
                <label>Database path</label>
                <input
                  type="text"
                  value={weightsHoursDbPath}
                  onChange={(event) => setWeightsHoursDbPath(event.target.value)}
                  placeholder="Ex: data/discipline_new.db"
                  className={styles.textInput}
                />
              </div>
              <div className={styles.buttonRow}>
                <button
                  className={styles.analyzeButton}
                  onClick={handleRunWeightsHoursCheck}
                  disabled={loading}
                >
                  {loading && activeAction === 'weights-hours' ? 'Se verifica...' : 'Run Weights & Hours Check'}
                </button>
              </div>
            </div>

            {weightsHoursResult ? (
              <section className={styles.qualityPanel}>
                {weightsSummary ? (
                  <div className={styles.metricGrid}>
                    <MetricCard label="Discipline" value={weightsSummary.total} />
                    <MetricCard label="OK" value={weightsSummary.ok} />
                    <MetricCard label="Not OK" value={weightsSummary.not_ok} />
                    <MetricCard label="Ore probleme" value={weightsSummary.hours_not_ok + weightsSummary.hours_missing} />
                    <MetricCard label="Ponderi probleme" value={weightsSummary.weights_not_ok + weightsSummary.weights_missing} />
                  </div>
                ) : null}

                <div className={styles.qualityToolbar}>
                  <p className={styles.qualityMeta}>
                    DB: <strong>{weightsHoursResult.db_path || '-'}</strong> | Saptamani: <strong>{weightsHoursResult.weeks ?? '-'}</strong>
                  </p>
                  <div className={styles.qualityFilterRow}>
                    <button
                      className={`${styles.filterButton} ${weightsHoursFilter === 'all' ? styles.filterButtonActive : ''}`}
                      onClick={() => setWeightsHoursFilter('all')}
                    >
                      Toate
                    </button>
                    <button
                      className={`${styles.filterButton} ${weightsHoursFilter === 'ok' ? styles.filterButtonActive : ''}`}
                      onClick={() => setWeightsHoursFilter('ok')}
                    >
                      OK
                    </button>
                    <button
                      className={`${styles.filterButton} ${weightsHoursFilter === 'not_ok' ? styles.filterButtonActive : ''}`}
                      onClick={() => setWeightsHoursFilter('not_ok')}
                    >
                      Not OK
                    </button>
                  </div>
                </div>

                {filteredWeightsRows.length === 0 ? (
                  <div className={styles.emptyState}>Nu exista rezultate pentru filtrul selectat.</div>
                ) : (
                  <div className={styles.qualityList}>
                    {filteredWeightsRows.map((row) => {
                      const weightsValues = Array.isArray(row?.weights?.values) ? row.weights.values : [];
                      const weightsValuesText = weightsValues.length > 0 ? weightsValues.join(' + ') : '-';
                      const hoursStatus = row?.hours?.status || 'missing';
                      const weightsStatus = row?.weights?.status || 'missing';

                      return (
                        <article
                          key={`weights-row-${row?.id ?? row?.cod ?? row?.nume}`}
                          className={`${styles.qualityCard} ${row?.overall_status === 'ok' ? styles.qualityCardOk : styles.qualityCardBad}`}
                        >
                          <div className={styles.qualityTopRow}>
                            <div>
                              <h3 className={styles.qualityTitle}>{row?.nume || 'Disciplina'}</h3>
                              <p className={styles.qualityMetaRow}>
                                Cod: {row?.cod || '-'} | Semestru: {row?.semestru ?? '-'} | Credite: {row?.credite ?? '-'}
                              </p>
                            </div>
                            <span className={`${styles.checkBadge} ${row?.overall_status === 'ok' ? styles.checkBadgeOk : styles.checkBadgeBad}`}>
                              {row?.overall_status === 'ok' ? 'OK' : 'NOT OK'}
                            </span>
                          </div>

                          <div className={styles.qualityCheckRow}>
                            <span className={`${styles.smallBadge} ${getCheckStatusClass(hoursStatus)}`}>
                              ORE {getCheckStatusLabel(hoursStatus)}
                            </span>
                            <span>{row?.hours?.message || '-'}</span>
                          </div>
                          <p className={styles.qualityHint}>
                            Calcul: {row?.hours?.ore_saptamana ?? '-'} x {weightsHoursResult.weeks ?? '-'} = {row?.hours?.expected_total ?? '-'} | total_ore_plan: {row?.hours?.total_ore_plan ?? '-'}
                          </p>

                          <div className={styles.qualityCheckRow}>
                            <span className={`${styles.smallBadge} ${getCheckStatusClass(weightsStatus)}`}>
                              PONDERI {getCheckStatusLabel(weightsStatus)}
                            </span>
                            <span>{row?.weights?.message || '-'}</span>
                          </div>
                          <p className={styles.qualityHint}>
                            Valori extrase: {weightsValuesText} | Suma: {row?.weights?.sum ?? '-'} | Sectiuni gasite: {row?.weights?.sections_found ?? 0} | Sursa: {row?.weights?.source || '-'}
                          </p>
                        </article>
                      );
                    })}
                  </div>
                )}
              </section>
            ) : null}
          </section>
        ) : viewMode === 'fdsingle' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Single FD Validator</h1>
            <p className={styles.infoText}>
              Incarca un singur PDF de fisa disciplina (text PDF, fara OCR) si vezi instant
              daca exista campuri lipsa sau erori matematice.
            </p>

            {error && <div className={styles.errorBox}>{error}</div>}

            <div className={styles.fdSingleUploadWrap}>
              <div
                className={`${styles.uploadCard} ${fdSingleFile ? styles.fileSelected : ''}`}
                onClick={() => fdSingleInputRef.current?.click()}
              >
                <div className={styles.uploadIcon}>{fdSingleFile ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>FD PDF</h3>
                <p>{fdSingleFile ? fdSingleFile.name : 'Upload fisa disciplinei'}</p>
                <input
                  ref={fdSingleInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'fdSingle')}
                />
              </div>
            </div>

            <div className={styles.buttonRow}>
              <button
                className={styles.analyzeButton}
                onClick={handleRunSingleFdValidation}
                disabled={!fdSingleFile || loading}
              >
                {loading && activeAction === 'fd-single' ? 'Se valideaza...' : 'Valideaza fisa'}
              </button>
            </div>

            {singleFdValidationResult ? (
              <section className={styles.fdResultPanel}>
                <div className={styles.metricGrid}>
                  <MetricCard label="Status" value={singleFdValidationResult.valid ? 'VALID' : 'INVALID'} />
                  <MetricCard label="Missing Fields" value={fdSingleMissing.length} />
                  <MetricCard label="Math Errors" value={fdSingleMathErrors.length} />
                  <MetricCard label="Disciplina" value={fdSingleCanonical?.nume_disciplina || '-'} />
                  <MetricCard label="Semestru" value={fdSingleCanonical?.semestru ?? '-'} />
                </div>

                <div className={`${styles.fdResultStatus} ${singleFdValidationResult.valid ? styles.fdResultStatusOk : styles.fdResultStatusBad}`}>
                  {singleFdValidationResult.valid
                    ? 'Validare trecuta: nu exista missing fields sau math errors.'
                    : 'Validare esuata: verifica detaliile de mai jos.'}
                </div>

                <div className={styles.fdIssuesGrid}>
                  <article className={`${styles.fdIssueCard} ${fdSingleMissing.length === 0 ? styles.fdIssueOk : styles.fdIssueBad}`}>
                    <h3>Missing Fields</h3>
                    {fdSingleMissing.length === 0 ? (
                      <p>Nu exista campuri lipsa.</p>
                    ) : (
                      <ul className={styles.fdIssueList}>
                        {fdSingleMissing.map((field) => (
                          <li key={field}>{field}</li>
                        ))}
                      </ul>
                    )}
                  </article>

                  <article className={`${styles.fdIssueCard} ${fdSingleMathErrors.length === 0 ? styles.fdIssueOk : styles.fdIssueBad}`}>
                    <h3>Math Errors</h3>
                    {fdSingleMathErrors.length === 0 ? (
                      <p>Nu exista erori matematice.</p>
                    ) : (
                      <ul className={styles.fdIssueList}>
                        {fdSingleMathErrors.map(([key, value]) => (
                          <li key={key}>
                            <strong>{key}</strong>: {String(value)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                </div>
              </section>
            ) : null}
          </section>
        ) : viewMode === 'fdprefill' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Single FD Template Prefill</h1>
            <p className={styles.infoText}>
              Incarca un PDF de fisa disciplina si genereaza un template FD precompletat,
              apoi exporta direct in Word pentru modificari.
            </p>

            {error && <div className={styles.errorBox}>{error}</div>}

            <div className={styles.fdSingleUploadWrap}>
              <div
                className={`${styles.uploadCard} ${fdPrefillFile ? styles.fileSelected : ''}`}
                onClick={() => fdPrefillInputRef.current?.click()}
              >
                <div className={styles.uploadIcon}>{fdPrefillFile ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>FD PDF</h3>
                <p>{fdPrefillFile ? fdPrefillFile.name : 'Upload fisa disciplinei'}</p>
                <input
                  ref={fdPrefillInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'fdPrefill')}
                />
              </div>
            </div>

            <div className={styles.buttonRow}>
              <button
                className={styles.analyzeButton}
                onClick={handleRunSingleFdPrefill}
                disabled={!fdPrefillFile || loading}
              >
                {loading && activeAction === 'fd-prefill' ? 'Se genereaza...' : 'Genereaza template precompletat'}
              </button>
            </div>

            {singleFdPrefillResult ? (
              <section className={styles.fdResultPanel}>
                <div className={styles.metricGrid}>
                  <MetricCard label="Status" value={singleFdPrefillResult.status?.toUpperCase() || '-'} />
                  <MetricCard label="Disciplina" value={fdPrefillMatchedDiscipline} />
                </div>

                <div className={`${styles.fdResultStatus} ${styles.fdResultStatusOk}`}>
                  Template-ul FD a fost generat cu succes.
                </div>

                {singleFdPrefillResult.output_html_url || singleFdPrefillResult.output_docx_url ? (
                  <div className={styles.buttonRow}>
                    {singleFdPrefillResult.output_html_url ? (
                      <a
                        className={styles.actionLinkButton}
                        href={singleFdPrefillResult.output_html_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Deschide template-ul precompletat
                      </a>
                    ) : null}
                    {singleFdPrefillResult.output_docx_url ? (
                      <a
                        className={styles.secondaryActionLinkButton}
                        href={singleFdPrefillResult.output_docx_url}
                        download
                      >
                        Export Word (.docx)
                      </a>
                    ) : null}
                  </div>
                ) : null}
              </section>
            ) : null}
          </section>
        ) : viewMode === 'fdmigrate' ? (
          <section className={styles.uploadSection}>
            <h1 className={styles.sectionTitle}>Migrare FD: Template Vechi -&gt; Template Nou</h1>
            <p className={styles.infoText}>
              Incarca fisa veche (PDF), construim modelul canonic si generam automat template-ul nou precompletat.
            </p>

            {error && <div className={styles.errorBox}>{error}</div>}

            <div className={styles.fdSingleUploadWrap}>
              <div
                className={`${styles.uploadCard} ${fdMigrationFile ? styles.fileSelected : ''}`}
                onClick={() => fdMigrationInputRef.current?.click()}
              >
                <div className={styles.uploadIcon}>{fdMigrationFile ? <CheckCircleIcon /> : <UploadIcon />}</div>
                <h3>FD Vechi (PDF)</h3>
                <p>{fdMigrationFile ? fdMigrationFile.name : 'Upload fisa disciplinei vechi'}</p>
                <input
                  ref={fdMigrationInputRef}
                  type="file"
                  accept="application/pdf"
                  className={styles.hiddenInput}
                  onChange={(event) => handleFileChange(event, 'fdMigration')}
                />
              </div>
            </div>

            <div className={styles.buttonRow}>
              <button
                className={styles.analyzeButton}
                onClick={handleRunSingleFdMigration}
                disabled={!fdMigrationFile || loading}
              >
                {loading && activeAction === 'fd-migrate' ? 'Se migreaza...' : 'Genereaza template nou'}
              </button>
            </div>

            {singleFdMigrationResult ? (
              <section className={styles.fdResultPanel}>
                <div className={styles.metricGrid}>
                  <MetricCard label="Status" value={singleFdMigrationResult.status?.toUpperCase() || '-'} />
                  <MetricCard label="Disciplina" value={fdMigrationMatchedDiscipline} />
                  <MetricCard label="Coverage Required" value={`${fdMigrationCoveragePercent.toFixed(2)}%`} />
                  <MetricCard label="Missing Required" value={fdMigrationMissingRequired.length} />
                </div>

                <div className={`${styles.fdResultStatus} ${styles.fdResultStatusOk}`}>
                  Migrarea in noul template s-a finalizat.
                </div>

                {singleFdMigrationResult.output_template_url || singleFdMigrationResult.output_docx_url ? (
                  <div className={styles.buttonRow}>
                    {singleFdMigrationResult.output_template_url ? (
                      <a
                        className={styles.actionLinkButton}
                        href={singleFdMigrationResult.output_template_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Deschide template-ul nou (JSON)
                      </a>
                    ) : null}
                    {singleFdMigrationResult.output_docx_url ? (
                      <a
                        className={styles.secondaryActionLinkButton}
                        href={singleFdMigrationResult.output_docx_url}
                        download
                      >
                        Export Word (.docx)
                      </a>
                    ) : null}
                  </div>
                ) : null}

                {singleFdMigrationResult.output_canonical_url || singleFdMigrationResult.output_report_url ? (
                  <div className={styles.subtleLinkRow}>
                    {singleFdMigrationResult.output_canonical_url ? (
                      <a
                        className={styles.textLink}
                        href={singleFdMigrationResult.output_canonical_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Model canonic (JSON)
                      </a>
                    ) : null}
                    {singleFdMigrationResult.output_report_url ? (
                      <a
                        className={styles.textLink}
                        href={singleFdMigrationResult.output_report_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Raport mapare
                      </a>
                    ) : null}
                  </div>
                ) : null}

                {fdMigrationMissingRequired.length > 0 ? (
                  <article className={`${styles.fdIssueCard} ${styles.fdIssueBad}`}>
                    <h3>Campuri obligatorii necompletate</h3>
                    <ul className={styles.fdIssueList}>
                      {fdMigrationMissingRequired.map((fieldName) => (
                        <li key={fieldName}>{fieldName}</li>
                      ))}
                    </ul>
                  </article>
                ) : null}

                {fdMigrationTemplatePreview ? (
                  <section className={styles.jsonPreview}>
                    <h3>Preview template nou</h3>
                    <pre className={styles.jsonCode}>
                      {JSON.stringify(fdMigrationTemplatePreview, null, 2)}
                    </pre>
                  </section>
                ) : null}
              </section>
            ) : null}
          </section>
        ) : viewMode === 'upload' ? (
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
