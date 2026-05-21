export const AnalyticsEvent = {
  login_success: 'login_success',
  login_failed: 'login_failed',
  signup_success: 'signup_success',
  signup_failed: 'signup_failed',
} as const;

export type AnalyticsEventName = (typeof AnalyticsEvent)[keyof typeof AnalyticsEvent];

type AnalyticsSource = 'auth_login' | 'auth_register' | (string & {});

type ErrorInfo = {
  status_code?: number;
  error_kind?: 'api_error' | 'network_error' | 'unknown_error';
};

export type AnalyticsEventParamsMap = {
  login_success: {
    user_id?: string;
    source: AnalyticsSource;
  };
  login_failed: {
    source: AnalyticsSource;
  } & ErrorInfo;
  signup_success: {
    user_id?: string;
    source: AnalyticsSource;
  };
  signup_failed: {
    source: AnalyticsSource;
  } & ErrorInfo;
};
