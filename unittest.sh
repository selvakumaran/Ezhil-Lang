#!/bin/bash

# run unit tests when previous bits passed
cd tests/unit/


if [ -e success.txt ];
then
    rm success.txt
fi
if [ -e failed.txt ];
then
    rm failed.txt
fi

touch success.txt
touch failed.txt

for i in `ls *.py`
do
    python $i
    if [ $? -eq 0 ]
    then
        echo $i >> success.txt
    else
        echo $i >> failed.txt
    fi
done

NFAIL=0 #ideall no unittests should fail
TOTFAIL=`wc -l failed.txt | cut -d' ' -f1`
echo "from sys import exit; exit( $TOTFAIL !=  $NFAIL )" | python
if [ $?  -eq 0 ]
then
   echo "Testing Successful!"
   exitcode=0 # success
else
   echo "Expecting $NFAIL failures, but found $TOTFAIL failures"
   echo "Too few/many failures; some negative tests may have failed"
   exitcode=255 #failed failures != $NFAIL
fi

# cleanup
rm failed.txt
rm success.txt
cd ../../
exit $exitcode
