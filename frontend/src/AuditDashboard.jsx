import React, { useState } from 'react';
import { Search, ChevronDown, ChevronUp, AlertCircle, CheckCircle2, Sparkles, BookOpen } from 'lucide-react';

const mockAuditData = [
  {
    fisa_id: 1,
    nume_materie: "Analiză Matematică",
    audit_tematica: {
      status: "VAG",
      explicatie: "Tematica cursului este prea generică, conținând doar termeni generali precum 'Introducere' și 'Partea 1', fără detalii specifice despre subiectele care vor fi acoperite.",
      sugestii_imbunatatire: [
        "Include subiecte specifice precum 'Limite și continuitate', 'Derivata și aplicațiile acesteia', 'Integrale definite și nedefinite'.",
        "Adaugă o structură detaliată a cursului, cu numărul de săptămâni dedicate fiecărui subiect."
      ]
    },
    audit_bibliografie: {
      status: "INVECHITA",
      cel_mai_nou_an_gasit: 1981,
      explicatie: "Toate titlurile din bibliografie sunt publicate înainte de 2021, ceea ce le face depășite pentru standardele actuale."
    }
  },
  {
    fisa_id: 2,
    nume_materie: "Fundamentele algebrice ale informaticii",
    audit_tematica: {
      status: "DETALIAT",
      explicatie: "Tematica este bine structurată și acoperă clar noțiunile fundamentale necesare.",
      sugestii_imbunatatire: []
    },
    audit_bibliografie: {
      status: "ACTUALIZATA",
      cel_mai_nou_an_gasit: 2023,
      explicatie: "Include publicații recente care reflectă stadiul actual al domeniului."
    }
  }
];

// Componenta mică pentru Badge-uri de Status
const StatusBadge = ({ status }) => {
  const isError = status === "VAG" || status === "INVECHITA";
  
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
      isError ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'
    }`}>
      {isError ? <AlertCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
      {status}
    </span>
  );
};

export default function AuditDashboard() {
  // Starea pentru search și pentru rândul deschis
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedRow, setExpandedRow] = useState(null);

  // Funcție pentru a deschide/închide rândul de detalii
  const toggleRow = (id) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  // Filtrarea datelor din tabel în funcție de search
  const filteredData = mockAuditData.filter(item => 
    item.nume_materie.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-6 max-w-6xl mx-auto bg-gray-50 min-h-screen">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Dashboard Audit AI</h1>
        <p className="text-gray-600">Asistent inteligent pentru verificarea calității Fișelor de Disciplină.</p>
      </div>

      {/* Bara de Search */}
      <div className="relative mb-6">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search className="h-5 w-5 text-gray-400" />
        </div>
        <input
          type="text"
          className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="Caută disciplina..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Tabelul Principal */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Disciplina</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Audit Tematică</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Audit Bibliografie</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Acțiuni</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredData.map((row) => (
              <React.Fragment key={row.fisa_id}>
                {/* Rândul principal sumar */}
                <tr 
                  className={`hover:bg-gray-50 cursor-pointer transition-colors ${expandedRow === row.fisa_id ? 'bg-blue-50' : ''}`}
                  onClick={() => toggleRow(row.fisa_id)}
                >
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">#{row.fisa_id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{row.nume_materie}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge type="tematica" status={row.audit_tematica.status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge type="bibliografie" status={row.audit_bibliografie.status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button className="text-blue-600 hover:text-blue-900 focus:outline-none">
                      {expandedRow === row.fisa_id ? <ChevronUp className="w-5 h-5 inline" /> : <ChevronDown className="w-5 h-5 inline" />}
                    </button>
                  </td>
                </tr>

                {/* Rândul Extins (Detaliile) */}
                {expandedRow === row.fisa_id && (
                  <tr>
                    <td colSpan={5} className="px-0 py-0">
                      <div className="bg-gray-50 border-t border-gray-200 px-6 py-6 grid grid-cols-1 md:grid-cols-2 gap-6 shadow-inner">
                        
                        {/* Panoul: Tematică */}
                        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                          <h3 className="text-lg font-semibold text-gray-800 flex items-center mb-3">
                            <BookOpen className="w-5 h-5 mr-2 text-blue-500" /> Analiză Tematică
                          </h3>
                          <p className="text-sm text-gray-600 mb-4 bg-gray-50 p-3 rounded border border-gray-100">
                            <strong>Feedback:</strong> {row.audit_tematica.explicatie}
                          </p>
                          
                          {row.audit_tematica.sugestii_imbunatatire.length > 0 && (
                            <div>
                              <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 flex items-center">
                                <Sparkles className="w-4 h-4 mr-1 text-amber-500" /> Sugestii AI Copilot
                              </h4>
                              <div className="space-y-2">
                                {row.audit_tematica.sugestii_imbunatatire.map((sugestie, idx) => (
                                  <div key={idx} className="group relative bg-blue-50 hover:bg-blue-100 border border-blue-200 p-3 rounded-md text-sm text-blue-900 transition-colors cursor-pointer">
                                    {sugestie}
                                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 font-medium">
                                      Click pentru copiere
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Panoul: Bibliografie */}
                        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
                          <h3 className="text-lg font-semibold text-gray-800 flex items-center mb-3">
                            <BookOpen className="w-5 h-5 mr-2 text-indigo-500" /> Analiză Bibliografie
                          </h3>
                          <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded border border-gray-100">
                            <strong>Feedback:</strong> {row.audit_bibliografie.explicatie}
                          </p>
                          <div className="mt-4 flex items-center">
                            <span className="text-sm text-gray-500 mr-2">Cel mai nou an detectat:</span>
                            <span className="px-2 py-1 bg-gray-100 rounded font-mono text-sm font-semibold text-gray-700">
                              {row.audit_bibliografie.cel_mai_nou_an_gasit || "N/A"}
                            </span>
                          </div>
                        </div>

                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        
        {filteredData.length === 0 && (
          <div className="text-center py-10">
            <p className="text-gray-500">Nu s-a găsit nicio materie.</p>
          </div>
        )}
      </div>
    </div>
  );
}
