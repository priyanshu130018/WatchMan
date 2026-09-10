import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
export const api = axios.create({ baseURL: API_BASE_URL, timeout: 20000 });

let accessToken: string | null = null;
export const setApiToken = (token: string | null) => { accessToken = token; };
export const getApiToken = () => accessToken;

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
