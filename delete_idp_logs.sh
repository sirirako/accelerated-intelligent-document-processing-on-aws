#!/bin/bash

echo "Getting all log groups with 'idp-' in name (case insensitive)..."
aws logs describe-log-groups --output text --query 'logGroups[].logGroupName' | tr '\t' '\n' | grep -i 'test' > idp_log_groups.txt

total=$(wc -l < idp_log_groups.txt)
echo "Found $total log groups to delete"

if [ $total -eq 0 ]; then
    echo "No log groups found"
    exit 0
fi

echo "Deleting log groups in batches of 50..."
split -l 50 idp_log_groups.txt batch_

batch_num=1
for batch_file in batch_*; do
    echo "Processing batch $batch_num..."
    
    # Delete each log group individually in parallel
    while IFS= read -r log_group; do
        {
            if aws logs delete-log-group --log-group-name "$log_group" 2>/dev/null; then
                echo "✓ Deleted: $log_group"
            else
                echo "✗ Failed: $log_group"
            fi
        } &
        
        # Limit to 10 concurrent processes
        (($(jobs -r | wc -l) >= 10)) && wait
    done < "$batch_file"
    
    # Wait for remaining jobs to complete
    wait
    
    echo "Batch $batch_num complete"
    ((batch_num++))
    sleep 1
done

echo "Cleanup..."
rm -f idp_log_groups.txt batch_*
echo "Done!"
