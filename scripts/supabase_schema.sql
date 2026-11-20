-- ============================================================================
-- SSCP Bridge Schema para Supabase (PostgreSQL) - Edicion Multi-Doctor
-- Caracteristicas:
--   1. Aislamiento estricto por doctor/estacion (clinic_id + secret_hash).
--   2. Cursor de sync incremental usando reloj del servidor (updated_at = now())
--      para no perder cambios por desfase de hora entre PC y celular.
--   3. RLS activado: acceso directo anon bloqueado; solo RPC autenticadas.
--   4. Compatible con Supabase Free Tier (solo deltas JSON livianos).
-- ============================================================================

-- 0. Extension pgcrypto para autenticacion segura dentro de RPCs
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA extensions;

-- 1. Tablas del Puente
CREATE TABLE IF NOT EXISTS public.clinic_stations (
    clinic_id         TEXT PRIMARY KEY,
    secret_hash       TEXT NOT NULL,
    doctor_name       TEXT,
    clinic_name       TEXT,
    specialty         TEXT,
    sede_name         TEXT,
    local_url         TEXT,
    tailscale_url     TEXT,
    app_version       TEXT,
    mobile_users_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.clinic_stations ADD COLUMN IF NOT EXISTS mobile_users_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS public.sync_patients (
    clinic_id               TEXT NOT NULL,
    client_uuid             TEXT NOT NULL,
    local_id                BIGINT,
    doctor_id               BIGINT,
    first_name              TEXT NOT NULL,
    last_name               TEXT NOT NULL,
    document_id             TEXT,
    date_of_birth           DATE,
    gender                  TEXT,
    phone                   TEXT,
    email                   TEXT,
    address                 TEXT,
    blood_type              TEXT,
    allergies               TEXT,
    insurance_name          TEXT,
    insurance_number        TEXT,
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    source_device           TEXT,
    client_updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, client_uuid)
);
CREATE INDEX IF NOT EXISTS idx_sync_patients_updated ON public.sync_patients (clinic_id, updated_at);

CREATE TABLE IF NOT EXISTS public.sync_appointments (
    clinic_id         TEXT NOT NULL,
    client_uuid       TEXT NOT NULL,
    local_id          BIGINT,
    patient_uuid      TEXT,
    patient_local_id  BIGINT,
    patient_name      TEXT,
    doctor_id         BIGINT,
    date              DATE NOT NULL,
    start_time        TEXT,
    end_time          TEXT,
    reason            TEXT,
    status            TEXT NOT NULL DEFAULT 'Pendiente',
    queue_number      INTEGER,
    service_id        BIGINT,
    service_name      TEXT,
    price                     DOUBLE PRECISION DEFAULT 0,
    notes                     TEXT,
    whatsapp_reminder_sent    BOOLEAN DEFAULT FALSE,
    whatsapp_reminder_sent_at TIMESTAMPTZ,
    source_device             TEXT,
    client_updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, client_uuid)
);
CREATE INDEX IF NOT EXISTS idx_sync_appointments_updated ON public.sync_appointments (clinic_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_appointments_date ON public.sync_appointments (clinic_id, date);
ALTER TABLE public.sync_appointments ADD COLUMN IF NOT EXISTS whatsapp_reminder_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE public.sync_appointments ADD COLUMN IF NOT EXISTS whatsapp_reminder_sent_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.sync_consultations (
    clinic_id            TEXT NOT NULL,
    client_uuid          TEXT NOT NULL,
    local_id             BIGINT,
    patient_uuid         TEXT,
    patient_local_id     BIGINT,
    appointment_uuid     TEXT,
    appointment_local_id BIGINT,
    doctor_id            BIGINT,
    doctor_name          TEXT,
    reason               TEXT,
    clinical_history     TEXT,
    symptoms             TEXT,
    physical_exam        TEXT,
    diagnosis            TEXT,
    treatment            TEXT,
    prescription         TEXT,
    notes                TEXT,
    is_first_visit       BOOLEAN DEFAULT FALSE,
    edit_version         INTEGER DEFAULT 1,
    created_at_iso       TIMESTAMPTZ,
    source_device        TEXT,
    client_updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, client_uuid)
);
CREATE INDEX IF NOT EXISTS idx_sync_consultations_updated ON public.sync_consultations (clinic_id, updated_at);

CREATE TABLE IF NOT EXISTS public.sync_payments (
    clinic_id            TEXT NOT NULL,
    client_uuid          TEXT NOT NULL,
    local_id             BIGINT,
    patient_uuid         TEXT,
    patient_local_id     BIGINT,
    appointment_uuid     TEXT,
    appointment_local_id BIGINT,
    service_id           BIGINT,
    service_name         TEXT,
    amount               DOUBLE PRECISION DEFAULT 0,
    discount             DOUBLE PRECISION DEFAULT 0,
    total                DOUBLE PRECISION DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'paid',
    payment_method       TEXT DEFAULT 'cash',
    insurance_name       TEXT,
    receipt_number       TEXT,
    notes                TEXT,
    created_at_iso       TIMESTAMPTZ,
    source_device        TEXT,
    client_updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, client_uuid)
);
CREATE INDEX IF NOT EXISTS idx_sync_payments_updated ON public.sync_payments (clinic_id, updated_at);

CREATE TABLE IF NOT EXISTS public.sync_services (
    clinic_id         TEXT NOT NULL,
    client_uuid       TEXT NOT NULL,
    local_id          BIGINT,
    name              TEXT NOT NULL,
    price             DOUBLE PRECISION DEFAULT 0,
    category          TEXT,
    color             TEXT,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    client_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (clinic_id, client_uuid)
);
CREATE INDEX IF NOT EXISTS idx_sync_services_updated ON public.sync_services (clinic_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_patients_clinic_local_id      ON public.sync_patients (clinic_id, local_id);
CREATE INDEX IF NOT EXISTS idx_sync_appointments_clinic_local_id  ON public.sync_appointments (clinic_id, local_id);
CREATE INDEX IF NOT EXISTS idx_sync_consultations_clinic_local_id ON public.sync_consultations (clinic_id, local_id);
CREATE INDEX IF NOT EXISTS idx_sync_payments_clinic_local_id      ON public.sync_payments (clinic_id, local_id);

-- Tabla Keep-Alive (sin PHI) declarada antes de RLS para instalaciones limpias
CREATE TABLE IF NOT EXISTS public.bridge_keepalive (
    id          INTEGER PRIMARY KEY,
    pinged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ping_count  BIGINT NOT NULL DEFAULT 1,
    last_source TEXT DEFAULT 'cron'
);

-- 2. Seguridad RLS (sin acceso publico directo a las tablas)
ALTER TABLE public.clinic_stations    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_patients      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_appointments  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_consultations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_payments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_services      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bridge_keepalive   ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
    public.clinic_stations,
    public.sync_patients,
    public.sync_appointments,
    public.sync_consultations,
    public.sync_payments,
    public.sync_services,
    public.bridge_keepalive
FROM anon, authenticated;

-- 3. Validacion interna de estacion/doctor
CREATE OR REPLACE FUNCTION public._sscp_assert_station(p_clinic_id TEXT, p_secret_hash TEXT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_hash TEXT;
BEGIN
    IF coalesce(trim(p_clinic_id), '') = '' OR coalesce(trim(p_secret_hash), '') = '' THEN
        RAISE EXCEPTION 'clinic_id y secret_hash son obligatorios';
    END IF;

    SELECT secret_hash INTO v_hash
    FROM public.clinic_stations
    WHERE clinic_id = trim(p_clinic_id);

    IF v_hash IS NULL OR v_hash <> trim(p_secret_hash) THEN
        RAISE EXCEPTION 'unauthorized_clinic_station';
    END IF;
END;
$$;
REVOKE ALL ON FUNCTION public._sscp_assert_station(TEXT, TEXT) FROM PUBLIC;

-- 4. Registro o heartbeat de PC del doctor (actualiza IP local/Tailscale y hashes de acceso remoto)
DROP FUNCTION IF EXISTS public.sscp_upsert_station(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.sscp_upsert_station(
    p_clinic_id     TEXT,
    p_secret_hash   TEXT,
    p_doctor_name   TEXT DEFAULT NULL,
    p_clinic_name   TEXT DEFAULT NULL,
    p_specialty     TEXT DEFAULT NULL,
    p_sede_name     TEXT DEFAULT NULL,
    p_local_url     TEXT DEFAULT NULL,
    p_tailscale_url TEXT DEFAULT NULL,
    p_app_version   TEXT DEFAULT NULL,
    p_mobile_users  JSONB DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_existing TEXT;
    v_cid TEXT := trim(coalesce(p_clinic_id, ''));
    v_hash TEXT := trim(coalesce(p_secret_hash, ''));
BEGIN
    IF v_cid = '' OR v_hash = '' THEN
        RAISE EXCEPTION 'clinic_id y secret_hash son obligatorios';
    END IF;

    SELECT secret_hash INTO v_existing
    FROM public.clinic_stations
    WHERE clinic_id = v_cid;

    IF v_existing IS NULL THEN
        INSERT INTO public.clinic_stations (
            clinic_id, secret_hash, doctor_name, clinic_name, specialty,
            sede_name, local_url, tailscale_url, app_version, mobile_users_json, last_seen_at, updated_at
        ) VALUES (
            v_cid, v_hash, p_doctor_name, p_clinic_name, p_specialty,
            p_sede_name, p_local_url, p_tailscale_url, p_app_version, coalesce(p_mobile_users, '[]'::jsonb), now(), now()
        );
    ELSIF v_existing <> v_hash THEN
        RAISE EXCEPTION 'unauthorized_clinic_station';
    ELSE
        UPDATE public.clinic_stations
        SET doctor_name       = coalesce(p_doctor_name, doctor_name),
            clinic_name       = coalesce(p_clinic_name, clinic_name),
            specialty         = coalesce(p_specialty, specialty),
            sede_name         = coalesce(p_sede_name, sede_name),
            local_url         = coalesce(p_local_url, local_url),
            tailscale_url     = coalesce(p_tailscale_url, tailscale_url),
            app_version       = coalesce(p_app_version, app_version),
            mobile_users_json = coalesce(p_mobile_users, mobile_users_json),
            last_seen_at      = now(),
            updated_at        = now()
        WHERE clinic_id = v_cid;
    END IF;

    RETURN jsonb_build_object('ok', true, 'clinic_id', v_cid, 'server_time', now());
END;
$$;

-- 4b. Login remoto directo por Supabase (sin depender de Wi-Fi local ni Tailscale)
CREATE OR REPLACE FUNCTION public.sscp_mobile_login(
    p_clinic_id   TEXT,
    p_secret_hash TEXT,
    p_email       TEXT,
    p_password    TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_cid TEXT := trim(coalesce(p_clinic_id, ''));
    v_email TEXT := lower(trim(coalesce(p_email, '')));
    v_st RECORD;
    v_u JSONB;
    v_hash TEXT;
    v_norm_hash TEXT;
BEGIN
    PERFORM public._sscp_assert_station(v_cid, p_secret_hash);

    IF v_email = '' OR coalesce(p_password, '') = '' THEN
        RETURN jsonb_build_object('ok', false, 'detail', 'Correo y contraseña requeridos.');
    END IF;

    SELECT clinic_id, doctor_name, clinic_name, specialty, sede_name, mobile_users_json
    INTO v_st
    FROM public.clinic_stations
    WHERE clinic_id = v_cid;

    FOR v_u IN SELECT * FROM jsonb_array_elements(coalesce(v_st.mobile_users_json, '[]'::jsonb)) LOOP
        IF lower(trim(coalesce(v_u->>'email', ''))) = v_email AND coalesce((v_u->>'is_active')::boolean, true) = true THEN
            v_hash := coalesce(v_u->>'password_hash', '');
            v_norm_hash := regexp_replace(v_hash, '^\$2[by]\$', '$2a$');
            IF v_norm_hash <> '' AND extensions.crypt(p_password, v_norm_hash) = v_norm_hash THEN
                RETURN jsonb_build_object(
                    'ok', true,
                    'access_token', 'supa-' || encode(extensions.digest(v_cid || ':' || v_email || ':' || now()::text, 'sha256'), 'hex'),
                    'user', jsonb_build_object(
                        'id', coalesce((v_u->>'id')::bigint, 1),
                        'name', coalesce(v_u->>'name', v_st.doctor_name, 'Usuario'),
                        'email', v_email,
                        'role', coalesce(v_u->>'role', 'doctor'),
                        'assigned_doctor_id', nullif(v_u->>'assigned_doctor_id', '')::bigint
                    ),
                    'clinic', jsonb_build_object(
                        'id', 1,
                        'name', coalesce(v_st.clinic_name, 'Centro Médico SSCP'),
                        'clinic_id', v_st.clinic_id,
                        'relay_channel_id', v_st.clinic_id,
                        'doctor_name', coalesce(v_st.doctor_name, 'Médico Especialista'),
                        'specialty', coalesce(v_st.specialty, 'Medicina General'),
                        'sede_name', coalesce(v_st.sede_name, 'Sede Central')
                    )
                );
            END IF;
        END IF;
    END LOOP;

    RETURN jsonb_build_object('ok', false, 'detail', 'Credenciales inválidas para este consultorio.');
END;
$$;

-- 5. Consultar endpoint actual de la PC (para auto-descubrimiento en APK)
CREATE OR REPLACE FUNCTION public.sscp_get_station(p_clinic_id TEXT, p_secret_hash TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row JSONB;
BEGIN
    PERFORM public._sscp_assert_station(p_clinic_id, p_secret_hash);

    SELECT jsonb_build_object(
        'clinic_id', clinic_id,
        'doctor_name', doctor_name,
        'clinic_name', clinic_name,
        'specialty', specialty,
        'sede_name', sede_name,
        'local_url', local_url,
        'tailscale_url', tailscale_url,
        'app_version', app_version,
        'last_seen_at', last_seen_at,
        'server_time', now()
    ) INTO v_row
    FROM public.clinic_stations
    WHERE clinic_id = trim(p_clinic_id);

    RETURN coalesce(v_row, '{}'::jsonb);
END;
$$;

-- 6. Empujar lote incremental (idempotente por client_uuid + Last-Write-Wins)
CREATE OR REPLACE FUNCTION public.sscp_push_batch(
    p_clinic_id     TEXT,
    p_secret_hash   TEXT,
    p_device_id     TEXT DEFAULT 'unknown',
    p_patients      JSONB DEFAULT '[]'::jsonb,
    p_appointments  JSONB DEFAULT '[]'::jsonb,
    p_consultations JSONB DEFAULT '[]'::jsonb,
    p_payments      JSONB DEFAULT '[]'::jsonb,
    p_services      JSONB DEFAULT '[]'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '25s'
AS $$
DECLARE
    v_cid TEXT := trim(p_clinic_id);
    v_elem JSONB;
    v_client_ts TIMESTAMPTZ;
    v_now TIMESTAMPTZ := clock_timestamp();
    v_cnt_p INT := 0;
    v_cnt_a INT := 0;
    v_cnt_c INT := 0;
    v_cnt_pay INT := 0;
    v_cnt_s INT := 0;
BEGIN
    PERFORM public._sscp_assert_station(v_cid, p_secret_hash);

    -- Pacientes
    FOR v_elem IN SELECT * FROM jsonb_array_elements(coalesce(p_patients, '[]'::jsonb)) LOOP
        v_client_ts := coalesce(nullif(v_elem->>'updated_at', '')::timestamptz, v_now);
        INSERT INTO public.sync_patients (
            clinic_id, client_uuid, local_id, doctor_id, first_name, last_name,
            document_id, date_of_birth, gender, phone, email, address, blood_type,
            allergies, insurance_name, insurance_number, emergency_contact_name,
            emergency_contact_phone, is_active, source_device, client_updated_at, updated_at
        ) VALUES (
            v_cid,
            v_elem->>'client_uuid',
            nullif(v_elem->>'local_id', '')::bigint,
            nullif(v_elem->>'doctor_id', '')::bigint,
            coalesce(v_elem->>'first_name', 'Paciente'),
            coalesce(v_elem->>'last_name', ''),
            nullif(v_elem->>'document_id', ''),
            nullif(v_elem->>'date_of_birth', '')::date,
            nullif(v_elem->>'gender', ''),
            nullif(v_elem->>'phone', ''),
            nullif(v_elem->>'email', ''),
            nullif(v_elem->>'address', ''),
            nullif(v_elem->>'blood_type', ''),
            nullif(v_elem->>'allergies', ''),
            coalesce(nullif(v_elem->>'insurance_name', ''), 'Privado / Particular'),
            nullif(v_elem->>'insurance_number', ''),
            nullif(v_elem->>'emergency_contact_name', ''),
            nullif(v_elem->>'emergency_contact_phone', ''),
            coalesce((v_elem->>'is_active')::boolean, true),
            coalesce(nullif(v_elem->>'source_device', ''), p_device_id),
            v_client_ts,
            v_now
        )
        ON CONFLICT (clinic_id, client_uuid) DO UPDATE SET
            local_id                = coalesce(EXCLUDED.local_id, sync_patients.local_id),
            doctor_id               = coalesce(EXCLUDED.doctor_id, sync_patients.doctor_id),
            first_name              = coalesce(nullif(EXCLUDED.first_name, ''), sync_patients.first_name),
            last_name               = coalesce(EXCLUDED.last_name, sync_patients.last_name),
            document_id             = coalesce(EXCLUDED.document_id, sync_patients.document_id),
            date_of_birth           = coalesce(EXCLUDED.date_of_birth, sync_patients.date_of_birth),
            gender                  = coalesce(EXCLUDED.gender, sync_patients.gender),
            phone                   = coalesce(EXCLUDED.phone, sync_patients.phone),
            email                   = coalesce(EXCLUDED.email, sync_patients.email),
            address                 = coalesce(EXCLUDED.address, sync_patients.address),
            blood_type              = coalesce(EXCLUDED.blood_type, sync_patients.blood_type),
            allergies               = coalesce(EXCLUDED.allergies, sync_patients.allergies),
            insurance_name          = coalesce(EXCLUDED.insurance_name, sync_patients.insurance_name),
            insurance_number        = coalesce(EXCLUDED.insurance_number, sync_patients.insurance_number),
            emergency_contact_name  = coalesce(EXCLUDED.emergency_contact_name, sync_patients.emergency_contact_name),
            emergency_contact_phone = coalesce(EXCLUDED.emergency_contact_phone, sync_patients.emergency_contact_phone),
            is_active               = coalesce(EXCLUDED.is_active, sync_patients.is_active),
            source_device           = EXCLUDED.source_device,
            client_updated_at       = greatest(EXCLUDED.client_updated_at, sync_patients.client_updated_at),
            updated_at              = v_now
        WHERE EXCLUDED.client_updated_at >= (sync_patients.client_updated_at - interval '5 minutes');
        v_cnt_p := v_cnt_p + 1;
    END LOOP;

    -- Citas
    FOR v_elem IN SELECT * FROM jsonb_array_elements(coalesce(p_appointments, '[]'::jsonb)) LOOP
        v_client_ts := coalesce(nullif(v_elem->>'updated_at', '')::timestamptz, v_now);
        INSERT INTO public.sync_appointments (
            clinic_id, client_uuid, local_id, patient_uuid, patient_local_id,
            patient_name, doctor_id, date, start_time, end_time, reason, status,
            queue_number, service_id, service_name, price, notes,
            whatsapp_reminder_sent, whatsapp_reminder_sent_at,
            source_device, client_updated_at, updated_at
        ) VALUES (
            v_cid,
            v_elem->>'client_uuid',
            nullif(v_elem->>'local_id', '')::bigint,
            nullif(v_elem->>'patient_uuid', ''),
            nullif(v_elem->>'patient_local_id', '')::bigint,
            nullif(v_elem->>'patient_name', ''),
            nullif(v_elem->>'doctor_id', '')::bigint,
            (v_elem->>'date')::date,
            nullif(v_elem->>'start_time', ''),
            nullif(v_elem->>'end_time', ''),
            coalesce(v_elem->>'reason', 'Consulta Médica'),
            coalesce(v_elem->>'status', 'Pendiente'),
            nullif(v_elem->>'queue_number', '')::integer,
            nullif(v_elem->>'service_id', '')::bigint,
            nullif(v_elem->>'service_name', ''),
            coalesce(nullif(v_elem->>'price', '')::double precision, 0),
            nullif(v_elem->>'notes', ''),
            coalesce(nullif(v_elem->>'whatsapp_reminder_sent', '')::boolean, false),
            nullif(v_elem->>'whatsapp_reminder_sent_at', '')::timestamptz,
            coalesce(nullif(v_elem->>'source_device', ''), p_device_id),
            v_client_ts,
            v_now
        )
        ON CONFLICT (clinic_id, client_uuid) DO UPDATE SET
            local_id                  = coalesce(EXCLUDED.local_id, sync_appointments.local_id),
            patient_uuid              = coalesce(EXCLUDED.patient_uuid, sync_appointments.patient_uuid),
            patient_local_id          = coalesce(EXCLUDED.patient_local_id, sync_appointments.patient_local_id),
            patient_name              = coalesce(EXCLUDED.patient_name, sync_appointments.patient_name),
            doctor_id                 = coalesce(EXCLUDED.doctor_id, sync_appointments.doctor_id),
            date                      = coalesce(EXCLUDED.date, sync_appointments.date),
            start_time                = coalesce(EXCLUDED.start_time, sync_appointments.start_time),
            end_time                  = coalesce(EXCLUDED.end_time, sync_appointments.end_time),
            reason                    = coalesce(EXCLUDED.reason, sync_appointments.reason),
            status                    = CASE
                WHEN lower(trim(coalesce(sync_appointments.status, ''))) IN (
                    'completada', 'atendida', 'listo', 'completed', 'finished',
                    'cancelada', 'anulada', 'canceled', 'cancelled', 'no_show', 'no asistió'
                )
                THEN sync_appointments.status
                WHEN lower(trim(coalesce(sync_appointments.status, ''))) IN ('en espera', 'en consulta')
                     AND lower(trim(coalesce(EXCLUDED.status, ''))) IN ('pendiente', 'confirmada', 'reagendada')
                     AND EXCLUDED.queue_number IS NOT NULL
                THEN sync_appointments.status
                ELSE coalesce(EXCLUDED.status, sync_appointments.status)
            END,
            queue_number              = coalesce(EXCLUDED.queue_number, sync_appointments.queue_number),
            service_id                = coalesce(EXCLUDED.service_id, sync_appointments.service_id),
            service_name              = coalesce(EXCLUDED.service_name, sync_appointments.service_name),
            price                     = coalesce(EXCLUDED.price, sync_appointments.price),
            notes                     = coalesce(EXCLUDED.notes, sync_appointments.notes),
            whatsapp_reminder_sent    = (coalesce(sync_appointments.whatsapp_reminder_sent, false) OR coalesce(EXCLUDED.whatsapp_reminder_sent, false)),
            whatsapp_reminder_sent_at = coalesce(sync_appointments.whatsapp_reminder_sent_at, EXCLUDED.whatsapp_reminder_sent_at),
            source_device             = EXCLUDED.source_device,
            client_updated_at         = greatest(EXCLUDED.client_updated_at, sync_appointments.client_updated_at),
            updated_at                = v_now
        WHERE EXCLUDED.client_updated_at >= (sync_appointments.client_updated_at - interval '5 minutes')
           OR (
               lower(coalesce(EXCLUDED.status, '')) IN ('completada', 'atendida', 'listo', 'cancelada', 'anulada')
               AND lower(coalesce(sync_appointments.status, '')) NOT IN ('completada', 'atendida', 'listo', 'cancelada', 'anulada')
           );
        v_cnt_a := v_cnt_a + 1;
    END LOOP;

    -- Consultas medicas
    FOR v_elem IN SELECT * FROM jsonb_array_elements(coalesce(p_consultations, '[]'::jsonb)) LOOP
        v_client_ts := coalesce(nullif(v_elem->>'updated_at', '')::timestamptz, v_now);
        INSERT INTO public.sync_consultations (
            clinic_id, client_uuid, local_id, patient_uuid, patient_local_id,
            appointment_uuid, appointment_local_id, doctor_id, doctor_name,
            reason, clinical_history, symptoms, physical_exam, diagnosis,
            treatment, prescription, notes, is_first_visit, edit_version,
            created_at_iso, source_device, client_updated_at, updated_at
        ) VALUES (
            v_cid,
            v_elem->>'client_uuid',
            nullif(v_elem->>'local_id', '')::bigint,
            nullif(v_elem->>'patient_uuid', ''),
            nullif(v_elem->>'patient_local_id', '')::bigint,
            nullif(v_elem->>'appointment_uuid', ''),
            nullif(v_elem->>'appointment_local_id', '')::bigint,
            nullif(v_elem->>'doctor_id', '')::bigint,
            nullif(v_elem->>'doctor_name', ''),
            nullif(v_elem->>'reason', ''),
            nullif(v_elem->>'clinical_history', ''),
            nullif(v_elem->>'symptoms', ''),
            nullif(v_elem->>'physical_exam', ''),
            nullif(v_elem->>'diagnosis', ''),
            nullif(v_elem->>'treatment', ''),
            nullif(v_elem->>'prescription', ''),
            nullif(v_elem->>'notes', ''),
            coalesce((v_elem->>'is_first_visit')::boolean, false),
            coalesce(nullif(v_elem->>'edit_version', '')::integer, 1),
            nullif(v_elem->>'created_at_iso', '')::timestamptz,
            coalesce(nullif(v_elem->>'source_device', ''), p_device_id),
            v_client_ts,
            v_now
        )
        ON CONFLICT (clinic_id, client_uuid) DO UPDATE SET
            local_id             = coalesce(EXCLUDED.local_id, sync_consultations.local_id),
            patient_uuid         = coalesce(EXCLUDED.patient_uuid, sync_consultations.patient_uuid),
            patient_local_id     = coalesce(EXCLUDED.patient_local_id, sync_consultations.patient_local_id),
            appointment_uuid     = coalesce(EXCLUDED.appointment_uuid, sync_consultations.appointment_uuid),
            appointment_local_id = coalesce(EXCLUDED.appointment_local_id, sync_consultations.appointment_local_id),
            doctor_name          = coalesce(EXCLUDED.doctor_name, sync_consultations.doctor_name),
            reason               = coalesce(EXCLUDED.reason, sync_consultations.reason),
            clinical_history     = coalesce(EXCLUDED.clinical_history, sync_consultations.clinical_history),
            symptoms             = coalesce(EXCLUDED.symptoms, sync_consultations.symptoms),
            physical_exam        = coalesce(EXCLUDED.physical_exam, sync_consultations.physical_exam),
            diagnosis            = coalesce(EXCLUDED.diagnosis, sync_consultations.diagnosis),
            treatment            = coalesce(EXCLUDED.treatment, sync_consultations.treatment),
            prescription         = coalesce(EXCLUDED.prescription, sync_consultations.prescription),
            notes                = coalesce(EXCLUDED.notes, sync_consultations.notes),
            edit_version         = greatest(coalesce(EXCLUDED.edit_version, 1), coalesce(sync_consultations.edit_version, 1)),
            source_device        = EXCLUDED.source_device,
            client_updated_at    = EXCLUDED.client_updated_at,
            updated_at           = v_now
        WHERE EXCLUDED.client_updated_at >= (sync_consultations.client_updated_at - interval '5 minutes')
           OR coalesce(EXCLUDED.edit_version, 1) > coalesce(sync_consultations.edit_version, 1);

        -- Garantizar en nube que toda consulta recibida complete su cita vinculada activa
        UPDATE public.sync_appointments
        SET status            = 'Completada',
            client_updated_at = greatest(sync_appointments.client_updated_at, v_now),
            updated_at        = v_now
        WHERE clinic_id = v_cid
          AND lower(trim(coalesce(status, ''))) IN (
              'pendiente', 'pending', 'confirmada', 'confirmed',
              'en espera', 'waiting', 'espera',
              'en consulta', 'en_consulta', 'in_consultation', 'in-consultation', 'atendiendo', 'consulting'
          )
          AND (
              (nullif(v_elem->>'appointment_uuid', '') IS NOT NULL AND client_uuid = nullif(v_elem->>'appointment_uuid', ''))
              OR (nullif(v_elem->>'appointment_local_id', '') IS NOT NULL AND local_id = nullif(v_elem->>'appointment_local_id', '')::bigint)
          );

        v_cnt_c := v_cnt_c + 1;
    END LOOP;

    -- Pagos
    FOR v_elem IN SELECT * FROM jsonb_array_elements(coalesce(p_payments, '[]'::jsonb)) LOOP
        v_client_ts := coalesce(nullif(v_elem->>'updated_at', '')::timestamptz, v_now);
        INSERT INTO public.sync_payments (
            clinic_id, client_uuid, local_id, patient_uuid, patient_local_id,
            appointment_uuid, appointment_local_id, service_id, service_name,
            amount, discount, total, status, payment_method, insurance_name,
            receipt_number, notes, created_at_iso, source_device,
            client_updated_at, updated_at
        ) VALUES (
            v_cid,
            v_elem->>'client_uuid',
            nullif(v_elem->>'local_id', '')::bigint,
            nullif(v_elem->>'patient_uuid', ''),
            nullif(v_elem->>'patient_local_id', '')::bigint,
            nullif(v_elem->>'appointment_uuid', ''),
            nullif(v_elem->>'appointment_local_id', '')::bigint,
            nullif(v_elem->>'service_id', '')::bigint,
            coalesce(v_elem->>'service_name', 'Consulta Médica General'),
            coalesce(nullif(v_elem->>'amount', '')::double precision, 0),
            coalesce(nullif(v_elem->>'discount', '')::double precision, 0),
            coalesce(nullif(v_elem->>'total', '')::double precision, 0),
            coalesce(v_elem->>'status', 'paid'),
            coalesce(v_elem->>'payment_method', 'cash'),
            coalesce(v_elem->>'insurance_name', 'Privado / Particular'),
            nullif(v_elem->>'receipt_number', ''),
            nullif(v_elem->>'notes', ''),
            nullif(v_elem->>'created_at_iso', '')::timestamptz,
            coalesce(nullif(v_elem->>'source_device', ''), p_device_id),
            v_client_ts,
            v_now
        )
        ON CONFLICT (clinic_id, client_uuid) DO UPDATE SET
            local_id             = coalesce(EXCLUDED.local_id, sync_payments.local_id),
            patient_uuid         = coalesce(EXCLUDED.patient_uuid, sync_payments.patient_uuid),
            patient_local_id     = coalesce(EXCLUDED.patient_local_id, sync_payments.patient_local_id),
            appointment_uuid     = coalesce(EXCLUDED.appointment_uuid, sync_payments.appointment_uuid),
            appointment_local_id = coalesce(EXCLUDED.appointment_local_id, sync_payments.appointment_local_id),
            service_id           = coalesce(EXCLUDED.service_id, sync_payments.service_id),
            service_name         = coalesce(EXCLUDED.service_name, sync_payments.service_name),
            amount               = coalesce(EXCLUDED.amount, sync_payments.amount),
            discount             = coalesce(EXCLUDED.discount, sync_payments.discount),
            total                = coalesce(EXCLUDED.total, sync_payments.total),
            status               = coalesce(EXCLUDED.status, sync_payments.status),
            payment_method       = coalesce(EXCLUDED.payment_method, sync_payments.payment_method),
            insurance_name       = coalesce(EXCLUDED.insurance_name, sync_payments.insurance_name),
            receipt_number       = coalesce(EXCLUDED.receipt_number, sync_payments.receipt_number),
            notes                = coalesce(EXCLUDED.notes, sync_payments.notes),
            source_device        = EXCLUDED.source_device,
            client_updated_at    = EXCLUDED.client_updated_at,
            updated_at           = v_now
        WHERE EXCLUDED.client_updated_at >= (sync_payments.client_updated_at - interval '5 minutes');
        v_cnt_pay := v_cnt_pay + 1;
    END LOOP;

    -- Catalogo de Servicios
    FOR v_elem IN SELECT * FROM jsonb_array_elements(coalesce(p_services, '[]'::jsonb)) LOOP
        v_client_ts := coalesce(nullif(v_elem->>'updated_at', '')::timestamptz, v_now);
        INSERT INTO public.sync_services (
            clinic_id, client_uuid, local_id, name, price, category, color, is_active,
            client_updated_at, updated_at
        ) VALUES (
            v_cid,
            v_elem->>'client_uuid',
            nullif(v_elem->>'local_id', '')::bigint,
            coalesce(v_elem->>'name', 'Consulta General'),
            coalesce(nullif(v_elem->>'price', '')::double precision, 0),
            coalesce(v_elem->>'category', 'Consulta'),
            coalesce(v_elem->>'color', '#3b82f6'),
            coalesce((v_elem->>'is_active')::boolean, true),
            v_client_ts,
            v_now
        )
        ON CONFLICT (clinic_id, client_uuid) DO UPDATE SET
            local_id          = coalesce(EXCLUDED.local_id, sync_services.local_id),
            name              = coalesce(EXCLUDED.name, sync_services.name),
            price             = coalesce(EXCLUDED.price, sync_services.price),
            category          = coalesce(EXCLUDED.category, sync_services.category),
            color             = coalesce(EXCLUDED.color, sync_services.color),
            is_active         = coalesce(EXCLUDED.is_active, sync_services.is_active),
            client_updated_at = EXCLUDED.client_updated_at,
            updated_at        = v_now
        WHERE EXCLUDED.client_updated_at >= (sync_services.client_updated_at - interval '5 minutes');
        v_cnt_s := v_cnt_s + 1;
    END LOOP;

    RETURN jsonb_build_object(
        'ok', true,
        'server_time', v_now,
        'counts', jsonb_build_object(
            'patients', v_cnt_p,
            'appointments', v_cnt_a,
            'consultations', v_cnt_c,
            'payments', v_cnt_pay,
            'services', v_cnt_s
        )
    );
END;
$$;

-- 7. Descargar solo cambios incrementales desde p_since
CREATE OR REPLACE FUNCTION public.sscp_pull_changes(
    p_clinic_id   TEXT,
    p_secret_hash TEXT,
    p_since       TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '25s'
AS $$
DECLARE
    v_cid TEXT := trim(p_clinic_id);
    v_cursor TIMESTAMPTZ := clock_timestamp();
BEGIN
    PERFORM public._sscp_assert_station(v_cid, p_secret_hash);

    RETURN jsonb_build_object(
        'ok', true,
        'server_time', v_cursor,
        'station', (
            SELECT coalesce(jsonb_build_object(
                'clinic_id', clinic_id,
                'doctor_name', doctor_name,
                'clinic_name', clinic_name,
                'specialty', specialty,
                'sede_name', sede_name,
                'local_url', local_url,
                'tailscale_url', tailscale_url,
                'app_version', app_version,
                'last_seen_at', last_seen_at
            ), '{}'::jsonb)
            FROM public.clinic_stations WHERE clinic_id = v_cid
        ),
        'patients', coalesce((
            SELECT jsonb_agg(to_jsonb(t))
            FROM (
                SELECT * FROM public.sync_patients
                WHERE clinic_id = v_cid AND (p_since IS NULL OR (updated_at > p_since AND updated_at <= v_cursor))
                ORDER BY updated_at ASC
                LIMIT 1000
            ) t
        ), '[]'::jsonb),
        'appointments', coalesce((
            SELECT jsonb_agg(to_jsonb(t))
            FROM (
                SELECT * FROM public.sync_appointments
                WHERE clinic_id = v_cid AND (p_since IS NULL OR (updated_at > p_since AND updated_at <= v_cursor))
                ORDER BY updated_at ASC
                LIMIT 1000
            ) t
        ), '[]'::jsonb),
        'consultations', coalesce((
            SELECT jsonb_agg(to_jsonb(t))
            FROM (
                SELECT * FROM public.sync_consultations
                WHERE clinic_id = v_cid AND (p_since IS NULL OR (updated_at > p_since AND updated_at <= v_cursor))
                ORDER BY updated_at ASC
                LIMIT 1000
            ) t
        ), '[]'::jsonb),
        'payments', coalesce((
            SELECT jsonb_agg(to_jsonb(t))
            FROM (
                SELECT * FROM public.sync_payments
                WHERE clinic_id = v_cid AND (p_since IS NULL OR (updated_at > p_since AND updated_at <= v_cursor))
                ORDER BY updated_at ASC
                LIMIT 1000
            ) t
        ), '[]'::jsonb),
        'services', coalesce((
            SELECT jsonb_agg(to_jsonb(t))
            FROM (
                SELECT * FROM public.sync_services
                WHERE clinic_id = v_cid AND (p_since IS NULL OR (updated_at > p_since AND updated_at <= v_cursor))
                ORDER BY updated_at ASC
                LIMIT 1000
            ) t
        ), '[]'::jsonb)
    );
END;
$$;

-- 8. Tabla y RPC Keep-Alive (sin PHI) para evitar pausa por 7 dias de inactividad en Free Tier
CREATE TABLE IF NOT EXISTS public.bridge_keepalive (
    id          INTEGER PRIMARY KEY,
    pinged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ping_count  BIGINT NOT NULL DEFAULT 1,
    last_source TEXT DEFAULT 'cron'
);
ALTER TABLE public.bridge_keepalive ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.sscp_keepalive(p_source TEXT DEFAULT 'cron')
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count BIGINT := 0;
    v_at TIMESTAMPTZ;
BEGIN
    INSERT INTO public.bridge_keepalive (id, pinged_at, ping_count, last_source)
    VALUES (1, now(), 1, coalesce(nullif(trim(p_source), ''), 'cron'))
    ON CONFLICT (id) DO UPDATE SET
        pinged_at   = now(),
        ping_count  = bridge_keepalive.ping_count + 1,
        last_source = EXCLUDED.last_source
    RETURNING ping_count, pinged_at INTO v_count, v_at;

    RETURN jsonb_build_object(
        'ok', true,
        'ping_count', v_count,
        'pinged_at', v_at
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.sscp_upsert_station(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sscp_mobile_login(TEXT, TEXT, TEXT, TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sscp_get_station(TEXT, TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sscp_push_batch(TEXT, TEXT, TEXT, JSONB, JSONB, JSONB, JSONB, JSONB) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sscp_pull_changes(TEXT, TEXT, TIMESTAMPTZ) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sscp_keepalive(TEXT) TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
