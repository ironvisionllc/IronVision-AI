import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "@/App";
import Layout from "@/components/Layout";
import { Calendar } from "@phosphor-icons/react";

const AuditsPage = ({ embedded = false }) => {
  const Wrap = embedded ? React.Fragment : Layout;
  const [audits, setAudits] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAudits();
  }, []);

  const fetchAudits = async () => {
    try {
      const response = await axios.get(`${API}/audits`);
      setAudits(response.data);
    } catch (error) {
      console.error("Failed to fetch audits", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Wrap>
      <div data-testid="audits-page">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight" style={{fontFamily: 'Inter, sans-serif'}}>Audit Management</h1>
          <p className="text-sm text-gray-600 mt-2">Schedule and track compliance audits</p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-gray-500">Loading audits...</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
            <Calendar size={48} weight="duotone" className="text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">Audit management features coming soon</p>
          </div>
        )}
      </div>
    </Wrap>
  );
};

export default AuditsPage;