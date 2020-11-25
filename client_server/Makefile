client: client.o clientConfigParser.o clientServerParserLib.o
	g++ client.o clientConfigParser.o clientServerParserLib.o -o client

client.o: client.cpp
	g++ -c client.cpp

clientConfigParser.o: clientConfigParser.cpp
	g++ -c clientConfigParser.cpp

clientServerParserLib.o: clientServerParserLib.cpp
	g++ -c clientServerParserLib.cpp

clean:
	rm -rf *.o client