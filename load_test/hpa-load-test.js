// Load test to exercise the evaluation-service HPA (and, indirectly, the
// analytics-service HPA, since /evaluate publishes an event to SQS per call).
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL;
if (!BASE_URL) {
  throw new Error('BASE_URL is required, e.g.: k6 run -e BASE_URL=http://<ingress-host> load_test/hpa-load-test.js');
}

const FLAG_NAME = __ENV.FLAG_NAME || 'demo-flag';

export const options = {
  stages: [
    { duration: '30s', target: 50 }, // ramp-up
    { duration: '3m', target: 50 },  // sustained load, enough to push the HPA past its 70% CPU target
    { duration: '30s', target: 0 },  // ramp-down, to watch the HPA scale back to minReplicas
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const userId = `k6-vu${__VU}-iter${__ITER}`;
  // tag "name" groups metrics by endpoint instead of by the unique per-request URL (avoids high-cardinality warning)
  const res = http.get(`${BASE_URL}/evaluation-service/evaluate?user_id=${userId}&flag_name=${FLAG_NAME}`, {
    tags: { name: 'evaluate' },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
