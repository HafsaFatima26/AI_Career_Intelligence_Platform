-- Run this in Supabase SQL Editor before starting Sitting 3

-- Add unique constraint on skill name for upsert to work
ALTER TABLE extracted_skills 
ADD CONSTRAINT extracted_skills_skill_unique UNIQUE (skill);

-- Verify the table structure
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'extracted_skills';
