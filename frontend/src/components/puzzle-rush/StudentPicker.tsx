'use client';

import type { SchoolStudent } from '@/lib/puzzle-rush/types';
import styles from './PuzzleRush.module.css';

export function studentName(s: SchoolStudent, fallback: string): string {
  return [s.first_name, s.last_name].filter(Boolean).join(' ') || fallback;
}

/** Family accounts: one pill per linked Chess Empire student. */
export default function StudentPicker({ students, value, label, fallbackName, onChange }: {
  students: SchoolStudent[];
  value: string | null;
  label: string;
  fallbackName: string;
  onChange: (studentId: string) => void;
}) {
  return (
    <div className={`${styles.seg} ${styles.studentSeg}`} role="radiogroup" aria-label={label}>
      {students.map((s) => (
        <button
          key={s.student_id}
          type="button"
          role="radio"
          aria-checked={s.student_id === value}
          className={`${styles.segButton} ${styles.studentButton} ${s.student_id === value ? styles.segOn : ''}`}
          onClick={() => onChange(s.student_id)}
        >
          {studentName(s, fallbackName)}
        </button>
      ))}
    </div>
  );
}
