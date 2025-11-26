import React, { useState } from 'react';
import PropTypes from 'prop-types';

/**
 * ScreeningForm - Formulario de screening individual
 * Campos: Nombre, Número de documento, Tipo de documento, Fecha de nacimiento, Nacionalidad, País
 */

// Tipos de documento disponibles
const DOCUMENT_TYPES = [
  { value: '', label: 'Seleccionar tipo...' },
  { value: 'passport', label: 'Pasaporte' },
  { value: 'cedula', label: 'Cédula de Identidad' },
  { value: 'ruc', label: 'RUC (Registro Único de Contribuyente)' },
  { value: 'license', label: 'Licencia de Conducir' },
  { value: 'other', label: 'Otro' }
];

// Lista de países (enfocado en región pero incluye principales)
const COUNTRIES = [
  { value: '', label: 'Seleccionar país...' },
  { value: 'PA', label: '🇵🇦 Panamá' },
  { value: 'CO', label: '🇨🇴 Colombia' },
  { value: 'VE', label: '🇻🇪 Venezuela' },
  { value: 'CR', label: '🇨🇷 Costa Rica' },
  { value: 'US', label: '🇺🇸 Estados Unidos' },
  { value: 'MX', label: '🇲🇽 México' },
  { value: 'BR', label: '🇧🇷 Brasil' },
  { value: 'AR', label: '🇦🇷 Argentina' },
  { value: 'CL', label: '🇨🇱 Chile' },
  { value: 'PE', label: '🇵🇪 Perú' },
  { value: 'EC', label: '🇪🇨 Ecuador' },
  { value: 'ES', label: '🇪🇸 España' },
  { value: 'CN', label: '🇨🇳 China' },
  { value: 'RU', label: '🇷🇺 Rusia' },
  { value: 'IR', label: '🇮🇷 Irán' },
  { value: 'OTHER', label: 'Otro' }
];

const INITIAL_FORM_STATE = {
  name: '',
  document_number: '',
  document_type: '',
  date_of_birth: '',
  nationality: '',
  country: ''
};

function ScreeningForm({ onSubmit, loading, disabled }) {
  const [formData, setFormData] = useState(INITIAL_FORM_STATE);
  const [errors, setErrors] = useState({});

  // Validar el formulario
  const validateForm = () => {
    const newErrors = {};
    
    if (!formData.name.trim()) {
      newErrors.name = 'El nombre es requerido';
    } else if (formData.name.trim().length < 2) {
      newErrors.name = 'El nombre debe tener al menos 2 caracteres';
    }

    // Validar fecha de nacimiento si se proporciona
    if (formData.date_of_birth) {
      const dob = new Date(formData.date_of_birth);
      const today = new Date();
      if (dob > today) {
        newErrors.date_of_birth = 'La fecha no puede ser futura';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Manejar cambios en los campos
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    
    // Limpiar error del campo cuando el usuario empieza a escribir
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: null
      }));
    }
  };

  // Manejar envío del formulario
  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }

    // Construir objeto de screening (solo incluir campos con valor)
    const screeningData = {
      name: formData.name.trim()
    };

    if (formData.document_number.trim()) {
      screeningData.document_number = formData.document_number.trim();
    }
    if (formData.document_type) {
      screeningData.document_type = formData.document_type;
    }
    if (formData.date_of_birth) {
      screeningData.date_of_birth = formData.date_of_birth;
    }
    if (formData.nationality) {
      screeningData.nationality = formData.nationality;
    }
    if (formData.country) {
      screeningData.country = formData.country;
    }

    onSubmit(screeningData);
  };

  // Limpiar formulario
  const handleClear = () => {
    setFormData(INITIAL_FORM_STATE);
    setErrors({});
  };

  return (
    <form onSubmit={handleSubmit} className="screening-form">
      <div className="form-header">
        <h2>🔍 Screening Individual</h2>
        <p className="form-description">
          Ingrese los datos de la persona a verificar contra las listas OFAC y ONU
        </p>
      </div>

      <div className="form-grid">
        {/* Nombre - Campo principal requerido */}
        <div className="form-group full-width">
          <label htmlFor="name">
            Nombre Completo <span className="required">*</span>
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            placeholder="Ej: Juan Carlos Pérez García"
            className={errors.name ? 'input-error' : ''}
            disabled={disabled || loading}
            autoComplete="off"
          />
          {errors.name && <span className="error-message">{errors.name}</span>}
        </div>

        {/* Número de documento */}
        <div className="form-group">
          <label htmlFor="document_number">Número de Documento</label>
          <input
            type="text"
            id="document_number"
            name="document_number"
            value={formData.document_number}
            onChange={handleChange}
            placeholder="Ej: 8-888-8888"
            disabled={disabled || loading}
            autoComplete="off"
          />
        </div>

        {/* Tipo de documento */}
        <div className="form-group">
          <label htmlFor="document_type">Tipo de Documento</label>
          <select
            id="document_type"
            name="document_type"
            value={formData.document_type}
            onChange={handleChange}
            disabled={disabled || loading}
          >
            {DOCUMENT_TYPES.map(type => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </div>

        {/* Fecha de nacimiento */}
        <div className="form-group">
          <label htmlFor="date_of_birth">Fecha de Nacimiento</label>
          <input
            type="date"
            id="date_of_birth"
            name="date_of_birth"
            value={formData.date_of_birth}
            onChange={handleChange}
            className={errors.date_of_birth ? 'input-error' : ''}
            disabled={disabled || loading}
          />
          {errors.date_of_birth && <span className="error-message">{errors.date_of_birth}</span>}
        </div>

        {/* Nacionalidad */}
        <div className="form-group">
          <label htmlFor="nationality">Nacionalidad</label>
          <select
            id="nationality"
            name="nationality"
            value={formData.nationality}
            onChange={handleChange}
            disabled={disabled || loading}
          >
            {COUNTRIES.map(country => (
              <option key={`nat-${country.value}`} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </div>

        {/* País de residencia */}
        <div className="form-group">
          <label htmlFor="country">País de Residencia</label>
          <select
            id="country"
            name="country"
            value={formData.country}
            onChange={handleChange}
            disabled={disabled || loading}
          >
            {COUNTRIES.map(country => (
              <option key={`country-${country.value}`} value={country.value}>
                {country.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Botones de acción */}
      <div className="form-actions">
        <button
          type="button"
          onClick={handleClear}
          className="btn btn-secondary"
          disabled={loading}
        >
          Limpiar
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={disabled || loading || !formData.name.trim()}
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Verificando...
            </>
          ) : (
            <>
              🔍 Verificar Persona
            </>
          )}
        </button>
      </div>
    </form>
  );
}

ScreeningForm.propTypes = {
  onSubmit: PropTypes.func.isRequired,
  loading: PropTypes.bool,
  disabled: PropTypes.bool
};

ScreeningForm.defaultProps = {
  loading: false,
  disabled: false
};

export default ScreeningForm;
