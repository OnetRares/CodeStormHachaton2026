import React, { useState, useRef } from 'react';
import styles from './Dashboard.module.css';

// SVG Icons
const UploadIcon = () => (
  <svg
    width="48"
    height="48"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="currentColor"
    stroke="currentColor"
    strokeWidth="2"
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const AlertCircleIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const LogoutIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const FileTextIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="12" y1="13" x2="12" y2="17" />
    <line x1="9" y1="15" x2="15" y2="15" />
  </svg>
);

const CheckmarkIcon = () => (
  <svg
    width="64"
    height="64"
    viewBox="0 0 24 24"
    fill="none"
    stroke="#16a34a"
    strokeWidth="3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="10" fill="#dcfce7" />
    <polyline points="8 12 11 15 16 9" />
  </svg>
);

export default function Dashboard() {
  const [dragActive, setDragActive] = useState({ fd: false, pi: false });
  const [fdFile, setFdFile] = useState(null);
  const [piFile, setPiFile] = useState(null);
  
  // Create refs for hidden file inputs
  const fdInputRef = useRef(null);
  const piInputRef = useRef(null);

  const handleDrag = (e, type) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive((prev) => ({ ...prev, [type]: true }));
    } else if (e.type === 'dragleave') {
      setDragActive((prev) => ({ ...prev, [type]: false }));
    }
  };

  const handleDrop = (e, type) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive((prev) => ({ ...prev, [type]: false }));
    
    // Get the dropped files
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0]; // Take only the first file
      if (type === 'fd') {
        setFdFile(file);
        console.log('FD file selected:', file.name);
      } else if (type === 'pi') {
        setPiFile(file);
        console.log('PI file selected:', file.name);
      }
    }
  };

  const handleFileChange = (e, type) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (type === 'fd') {
        setFdFile(file);
        console.log('FD file selected:', file.name);
      } else if (type === 'pi') {
        setPiFile(file);
        console.log('PI file selected:', file.name);
      }
    }
  };

  const handleCardClick = (inputRef) => {
    inputRef.current?.click();
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  // Mock validation data
  const validationData = [
    {
      id: 1,
      documentType: 'Fișa de Disciplină (FD)',
      status: 'Invalid',
      statusType: 'error',
      message: 'Missing evaluation weight in assessment section',
    },
    {
      id: 2,
      documentType: 'Plan de Învățământ (PI)',
      status: 'Valid',
      statusType: 'success',
      message: 'All required fields present',
    },
    {
      id: 3,
      documentType: 'Fișa de Disciplină (FD)',
      status: 'Warning',
      statusType: 'warning',
      message: 'Incomplete bibliography section',
    },
  ];

  const handleLogout = () => {
    console.log('Logging out...');
    // Implement logout logic
  };

  return (
    <div className={styles.container}>
      {/* Header/Navbar */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.logo}>📚 DocManage</div>
        </div>
        <button
          className={styles.logoutButton}
          onClick={handleLogout}
          title="Logout"
        >
          <LogoutIcon />
          <span>Logout</span>
        </button>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        {/* Upload Section */}
        <section className={styles.uploadSection}>
          <h1 className={styles.sectionTitle}>Upload Documents</h1>
          <div className={styles.uploadCardsContainer}>
            {/* FD Upload Card */}
            <div
              className={`${styles.uploadCard} ${
                dragActive.fd ? styles.dragActive : ''
              } ${fdFile ? styles.fileSelected : ''}`}
              onDragEnter={(e) => handleDrag(e, 'fd')}
              onDragLeave={(e) => handleDrag(e, 'fd')}
              onDragOver={(e) => handleDrag(e, 'fd')}
              onDrop={(e) => handleDrop(e, 'fd')}
              onClick={() => handleCardClick(fdInputRef)}
              style={{ cursor: 'pointer' }}
            >
              <div className={styles.uploadIcon}>
                {fdFile ? <CheckmarkIcon /> : <UploadIcon />}
              </div>
              <h3 className={styles.uploadTitle}>
                {fdFile ? 'File Selected' : 'Upload Fișa de Disciplină (FD)'}
              </h3>
              {fdFile ? (
                <div className={styles.fileInfo}>
                  <p className={styles.fileName}>{fdFile.name}</p>
                  <p className={styles.fileSize}>{formatFileSize(fdFile.size)}</p>
                </div>
              ) : (
                <p className={styles.uploadSubtext}>
                  Drag and drop your file here or click to browse
                </p>
              )}
              <input
                ref={fdInputRef}
                type="file"
                className={styles.hiddenInput}
                accept=".pdf,.doc,.docx"
                onChange={(e) => handleFileChange(e, 'fd')}
              />
            </div>

            {/* PI Upload Card */}
            <div
              className={`${styles.uploadCard} ${
                dragActive.pi ? styles.dragActive : ''
              } ${piFile ? styles.fileSelected : ''}`}
              onDragEnter={(e) => handleDrag(e, 'pi')}
              onDragLeave={(e) => handleDrag(e, 'pi')}
              onDragOver={(e) => handleDrag(e, 'pi')}
              onDrop={(e) => handleDrop(e, 'pi')}
              onClick={() => handleCardClick(piInputRef)}
              style={{ cursor: 'pointer' }}
            >
              <div className={styles.uploadIcon}>
                {piFile ? <CheckmarkIcon /> : <UploadIcon />}
              </div>
              <h3 className={styles.uploadTitle}>
                {piFile ? 'File Selected' : 'Upload Plan de Învățământ (PI)'}
              </h3>
              {piFile ? (
                <div className={styles.fileInfo}>
                  <p className={styles.fileName}>{piFile.name}</p>
                  <p className={styles.fileSize}>{formatFileSize(piFile.size)}</p>
                </div>
              ) : (
                <p className={styles.uploadSubtext}>
                  Drag and drop your file here or click to browse
                </p>
              )}
              <input
                ref={piInputRef}
                type="file"
                className={styles.hiddenInput}
                accept=".pdf,.doc,.docx"
                onChange={(e) => handleFileChange(e, 'pi')}
              />
            </div>
          </div>
        </section>

        {/* Validation Results Section */}
        <section className={styles.validationSection}>
          <h2 className={styles.sectionTitle}>Validation Status</h2>
          <div className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Document Type</th>
                  <th>Status</th>
                  <th>Details</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {validationData.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <div className={styles.documentCell}>
                        <FileTextIcon />
                        <span>{row.documentType}</span>
                      </div>
                    </td>
                    <td>
                      <div
                        className={`${styles.statusBadge} ${
                          styles[`status-${row.statusType}`]
                        }`}
                      >
                        {row.statusType === 'success' && <CheckCircleIcon />}
                        {row.statusType !== 'success' && <AlertCircleIcon />}
                        <span>{row.status}</span>
                      </div>
                    </td>
                    <td className={styles.detailsCell}>{row.message}</td>
                    <td>
                      <button
                        className={styles.actionButton}
                        onClick={() =>
                          console.log(`View details for ${row.id}`)
                        }
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
