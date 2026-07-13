#define SOUFFLE_GENERATOR_VERSION "2.4.1"
#include <chrono>
#include <iostream>
#include "souffle/CompiledSouffle.h"
#include "souffle/SignalHandler.h"
#include "souffle/SouffleInterface.h"
#include "souffle/datastructure/BTree.h"
#include "souffle/io/IOSystem.h"
#include <any>
namespace functors {
extern "C" {
}
} //namespace functors
namespace souffle::t_btree_iiii__1_3_0_2__1111__0101 {
using namespace souffle;
struct Type {
static constexpr Relation::arity_type Arity = 4;
using t_tuple = Tuple<RamDomain, 4>;
struct t_comparator_0{
 int operator()(const t_tuple& a, const t_tuple& b) const {
  return (ramBitCast<RamSigned>(a[1]) < ramBitCast<RamSigned>(b[1])) ? -1 : (ramBitCast<RamSigned>(a[1]) > ramBitCast<RamSigned>(b[1])) ? 1 :((ramBitCast<RamSigned>(a[3]) < ramBitCast<RamSigned>(b[3])) ? -1 : (ramBitCast<RamSigned>(a[3]) > ramBitCast<RamSigned>(b[3])) ? 1 :((ramBitCast<RamSigned>(a[0]) < ramBitCast<RamSigned>(b[0])) ? -1 : (ramBitCast<RamSigned>(a[0]) > ramBitCast<RamSigned>(b[0])) ? 1 :((ramBitCast<RamSigned>(a[2]) < ramBitCast<RamSigned>(b[2])) ? -1 : (ramBitCast<RamSigned>(a[2]) > ramBitCast<RamSigned>(b[2])) ? 1 :(0))));
 }
bool less(const t_tuple& a, const t_tuple& b) const {
  return (ramBitCast<RamSigned>(a[1]) < ramBitCast<RamSigned>(b[1]))|| ((ramBitCast<RamSigned>(a[1]) == ramBitCast<RamSigned>(b[1])) && ((ramBitCast<RamSigned>(a[3]) < ramBitCast<RamSigned>(b[3]))|| ((ramBitCast<RamSigned>(a[3]) == ramBitCast<RamSigned>(b[3])) && ((ramBitCast<RamSigned>(a[0]) < ramBitCast<RamSigned>(b[0]))|| ((ramBitCast<RamSigned>(a[0]) == ramBitCast<RamSigned>(b[0])) && ((ramBitCast<RamSigned>(a[2]) < ramBitCast<RamSigned>(b[2]))))))));
 }
bool equal(const t_tuple& a, const t_tuple& b) const {
return (ramBitCast<RamSigned>(a[1]) == ramBitCast<RamSigned>(b[1]))&&(ramBitCast<RamSigned>(a[3]) == ramBitCast<RamSigned>(b[3]))&&(ramBitCast<RamSigned>(a[0]) == ramBitCast<RamSigned>(b[0]))&&(ramBitCast<RamSigned>(a[2]) == ramBitCast<RamSigned>(b[2]));
 }
};
using t_ind_0 = btree_set<t_tuple,t_comparator_0>;
t_ind_0 ind_0;
using iterator = t_ind_0::iterator;
struct context {
t_ind_0::operation_hints hints_0_lower;
t_ind_0::operation_hints hints_0_upper;
};
context createContext() { return context(); }
bool insert(const t_tuple& t);
bool insert(const t_tuple& t, context& h);
bool insert(const RamDomain* ramDomain);
bool insert(RamDomain a0,RamDomain a1,RamDomain a2,RamDomain a3);
bool contains(const t_tuple& t, context& h) const;
bool contains(const t_tuple& t) const;
std::size_t size() const;
iterator find(const t_tuple& t, context& h) const;
iterator find(const t_tuple& t) const;
range<iterator> lowerUpperRange_0000(const t_tuple& /* lower */, const t_tuple& /* upper */, context& /* h */) const;
range<iterator> lowerUpperRange_0000(const t_tuple& /* lower */, const t_tuple& /* upper */) const;
range<t_ind_0::iterator> lowerUpperRange_1111(const t_tuple& lower, const t_tuple& upper, context& h) const;
range<t_ind_0::iterator> lowerUpperRange_1111(const t_tuple& lower, const t_tuple& upper) const;
range<t_ind_0::iterator> lowerUpperRange_0101(const t_tuple& lower, const t_tuple& upper, context& h) const;
range<t_ind_0::iterator> lowerUpperRange_0101(const t_tuple& lower, const t_tuple& upper) const;
bool empty() const;
std::vector<range<iterator>> partition() const;
void purge();
iterator begin() const;
iterator end() const;
void printStatistics(std::ostream& o) const;
};
} // namespace souffle::t_btree_iiii__1_3_0_2__1111__0101 
namespace souffle::t_btree_iiii__1_3_0_2__1111__0101 {
using namespace souffle;
using t_ind_0 = Type::t_ind_0;
using iterator = Type::iterator;
using context = Type::context;
bool Type::insert(const t_tuple& t) {
context h;
return insert(t, h);
}
bool Type::insert(const t_tuple& t, context& h) {
if (ind_0.insert(t, h.hints_0_lower)) {
return true;
} else return false;
}
bool Type::insert(const RamDomain* ramDomain) {
RamDomain data[4];
std::copy(ramDomain, ramDomain + 4, data);
const t_tuple& tuple = reinterpret_cast<const t_tuple&>(data);
context h;
return insert(tuple, h);
}
bool Type::insert(RamDomain a0,RamDomain a1,RamDomain a2,RamDomain a3) {
RamDomain data[4] = {a0,a1,a2,a3};
return insert(data);
}
bool Type::contains(const t_tuple& t, context& h) const {
return ind_0.contains(t, h.hints_0_lower);
}
bool Type::contains(const t_tuple& t) const {
context h;
return contains(t, h);
}
std::size_t Type::size() const {
return ind_0.size();
}
iterator Type::find(const t_tuple& t, context& h) const {
return ind_0.find(t, h.hints_0_lower);
}
iterator Type::find(const t_tuple& t) const {
context h;
return find(t, h);
}
range<iterator> Type::lowerUpperRange_0000(const t_tuple& /* lower */, const t_tuple& /* upper */, context& /* h */) const {
return range<iterator>(ind_0.begin(),ind_0.end());
}
range<iterator> Type::lowerUpperRange_0000(const t_tuple& /* lower */, const t_tuple& /* upper */) const {
return range<iterator>(ind_0.begin(),ind_0.end());
}
range<t_ind_0::iterator> Type::lowerUpperRange_1111(const t_tuple& lower, const t_tuple& upper, context& h) const {
t_comparator_0 comparator;
int cmp = comparator(lower, upper);
if (cmp == 0) {
    auto pos = ind_0.find(lower, h.hints_0_lower);
    auto fin = ind_0.end();
    if (pos != fin) {fin = pos; ++fin;}
    return make_range(pos, fin);
}
if (cmp > 0) {
    return make_range(ind_0.end(), ind_0.end());
}
return make_range(ind_0.lower_bound(lower, h.hints_0_lower), ind_0.upper_bound(upper, h.hints_0_upper));
}
range<t_ind_0::iterator> Type::lowerUpperRange_1111(const t_tuple& lower, const t_tuple& upper) const {
context h;
return lowerUpperRange_1111(lower,upper,h);
}
range<t_ind_0::iterator> Type::lowerUpperRange_0101(const t_tuple& lower, const t_tuple& upper, context& h) const {
t_comparator_0 comparator;
int cmp = comparator(lower, upper);
if (cmp > 0) {
    return make_range(ind_0.end(), ind_0.end());
}
return make_range(ind_0.lower_bound(lower, h.hints_0_lower), ind_0.upper_bound(upper, h.hints_0_upper));
}
range<t_ind_0::iterator> Type::lowerUpperRange_0101(const t_tuple& lower, const t_tuple& upper) const {
context h;
return lowerUpperRange_0101(lower,upper,h);
}
bool Type::empty() const {
return ind_0.empty();
}
std::vector<range<iterator>> Type::partition() const {
return ind_0.getChunks(400);
}
void Type::purge() {
ind_0.clear();
}
iterator Type::begin() const {
return ind_0.begin();
}
iterator Type::end() const {
return ind_0.end();
}
void Type::printStatistics(std::ostream& o) const {
o << " arity 4 direct b-tree index 0 lex-order [1,3,0,2]\n";
ind_0.printStats(o);
}
} // namespace souffle::t_btree_iiii__1_3_0_2__1111__0101 
namespace souffle::t_btree_i__0__1 {
using namespace souffle;
struct Type {
static constexpr Relation::arity_type Arity = 1;
using t_tuple = Tuple<RamDomain, 1>;
struct t_comparator_0{
 int operator()(const t_tuple& a, const t_tuple& b) const {
  return (ramBitCast<RamSigned>(a[0]) < ramBitCast<RamSigned>(b[0])) ? -1 : (ramBitCast<RamSigned>(a[0]) > ramBitCast<RamSigned>(b[0])) ? 1 :(0);
 }
bool less(const t_tuple& a, const t_tuple& b) const {
  return (ramBitCast<RamSigned>(a[0]) < ramBitCast<RamSigned>(b[0]));
 }
bool equal(const t_tuple& a, const t_tuple& b) const {
return (ramBitCast<RamSigned>(a[0]) == ramBitCast<RamSigned>(b[0]));
 }
};
using t_ind_0 = btree_set<t_tuple,t_comparator_0>;
t_ind_0 ind_0;
using iterator = t_ind_0::iterator;
struct context {
t_ind_0::operation_hints hints_0_lower;
t_ind_0::operation_hints hints_0_upper;
};
context createContext() { return context(); }
bool insert(const t_tuple& t);
bool insert(const t_tuple& t, context& h);
bool insert(const RamDomain* ramDomain);
bool insert(RamDomain a0);
bool contains(const t_tuple& t, context& h) const;
bool contains(const t_tuple& t) const;
std::size_t size() const;
iterator find(const t_tuple& t, context& h) const;
iterator find(const t_tuple& t) const;
range<iterator> lowerUpperRange_0(const t_tuple& /* lower */, const t_tuple& /* upper */, context& /* h */) const;
range<iterator> lowerUpperRange_0(const t_tuple& /* lower */, const t_tuple& /* upper */) const;
range<t_ind_0::iterator> lowerUpperRange_1(const t_tuple& lower, const t_tuple& upper, context& h) const;
range<t_ind_0::iterator> lowerUpperRange_1(const t_tuple& lower, const t_tuple& upper) const;
bool empty() const;
std::vector<range<iterator>> partition() const;
void purge();
iterator begin() const;
iterator end() const;
void printStatistics(std::ostream& o) const;
};
} // namespace souffle::t_btree_i__0__1 
namespace souffle::t_btree_i__0__1 {
using namespace souffle;
using t_ind_0 = Type::t_ind_0;
using iterator = Type::iterator;
using context = Type::context;
bool Type::insert(const t_tuple& t) {
context h;
return insert(t, h);
}
bool Type::insert(const t_tuple& t, context& h) {
if (ind_0.insert(t, h.hints_0_lower)) {
return true;
} else return false;
}
bool Type::insert(const RamDomain* ramDomain) {
RamDomain data[1];
std::copy(ramDomain, ramDomain + 1, data);
const t_tuple& tuple = reinterpret_cast<const t_tuple&>(data);
context h;
return insert(tuple, h);
}
bool Type::insert(RamDomain a0) {
RamDomain data[1] = {a0};
return insert(data);
}
bool Type::contains(const t_tuple& t, context& h) const {
return ind_0.contains(t, h.hints_0_lower);
}
bool Type::contains(const t_tuple& t) const {
context h;
return contains(t, h);
}
std::size_t Type::size() const {
return ind_0.size();
}
iterator Type::find(const t_tuple& t, context& h) const {
return ind_0.find(t, h.hints_0_lower);
}
iterator Type::find(const t_tuple& t) const {
context h;
return find(t, h);
}
range<iterator> Type::lowerUpperRange_0(const t_tuple& /* lower */, const t_tuple& /* upper */, context& /* h */) const {
return range<iterator>(ind_0.begin(),ind_0.end());
}
range<iterator> Type::lowerUpperRange_0(const t_tuple& /* lower */, const t_tuple& /* upper */) const {
return range<iterator>(ind_0.begin(),ind_0.end());
}
range<t_ind_0::iterator> Type::lowerUpperRange_1(const t_tuple& lower, const t_tuple& upper, context& h) const {
t_comparator_0 comparator;
int cmp = comparator(lower, upper);
if (cmp == 0) {
    auto pos = ind_0.find(lower, h.hints_0_lower);
    auto fin = ind_0.end();
    if (pos != fin) {fin = pos; ++fin;}
    return make_range(pos, fin);
}
if (cmp > 0) {
    return make_range(ind_0.end(), ind_0.end());
}
return make_range(ind_0.lower_bound(lower, h.hints_0_lower), ind_0.upper_bound(upper, h.hints_0_upper));
}
range<t_ind_0::iterator> Type::lowerUpperRange_1(const t_tuple& lower, const t_tuple& upper) const {
context h;
return lowerUpperRange_1(lower,upper,h);
}
bool Type::empty() const {
return ind_0.empty();
}
std::vector<range<iterator>> Type::partition() const {
return ind_0.getChunks(400);
}
void Type::purge() {
ind_0.clear();
}
iterator Type::begin() const {
return ind_0.begin();
}
iterator Type::end() const {
return ind_0.end();
}
void Type::printStatistics(std::ostream& o) const {
o << " arity 1 direct b-tree index 0 lex-order [0]\n";
ind_0.printStats(o);
}
} // namespace souffle::t_btree_i__0__1 
namespace  souffle {
using namespace souffle;
class Stratum_edge_9543a759b165a2cb {
public:
 Stratum_edge_9543a759b165a2cb(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_iiii__1_3_0_2__1111__0101::Type& rel_edge_04d25f5060e9043b);
void run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret);
private:
SymbolTable& symTable;
RecordTable& recordTable;
ConcurrentCache<std::string,std::regex>& regexCache;
bool& pruneImdtRels;
bool& performIO;
SignalHandler*& signalHandler;
std::atomic<std::size_t>& iter;
std::atomic<RamDomain>& ctr;
std::string& inputDirectory;
std::string& outputDirectory;
t_btree_iiii__1_3_0_2__1111__0101::Type* rel_edge_04d25f5060e9043b;
};
} // namespace  souffle
namespace  souffle {
using namespace souffle;
 Stratum_edge_9543a759b165a2cb::Stratum_edge_9543a759b165a2cb(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_iiii__1_3_0_2__1111__0101::Type& rel_edge_04d25f5060e9043b):
symTable(symTable),
recordTable(recordTable),
regexCache(regexCache),
pruneImdtRels(pruneImdtRels),
performIO(performIO),
signalHandler(signalHandler),
iter(iter),
ctr(ctr),
inputDirectory(inputDirectory),
outputDirectory(outputDirectory),
rel_edge_04d25f5060e9043b(&rel_edge_04d25f5060e9043b){
}

void Stratum_edge_9543a759b165a2cb::run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret){
if (performIO) {
try {std::map<std::string, std::string> directiveMap({{"IO","file"},{"attributeNames","subj\tpred\tobj\tneg"},{"auxArity","0"},{"columns","16:0:17:3"},{"fact-dir","."},{"filename","rtx-kg2_edges_2.8.1.tsv"},{"name","edge"},{"operation","input"},{"params","{\"records\": {}, \"relation\": {\"arity\": 4, \"params\": [\"subj\", \"pred\", \"obj\", \"neg\"]}}"},{"types","{\"ADTs\": {}, \"records\": {}, \"relation\": {\"arity\": 4, \"types\": [\"s:symbol\", \"s:symbol\", \"s:symbol\", \"s:symbol\"]}}"}});
if (!inputDirectory.empty()) {directiveMap["fact-dir"] = inputDirectory;}
IOSystem::getInstance().getReader(directiveMap, symTable, recordTable)->readAll(*rel_edge_04d25f5060e9043b);
} catch (std::exception& e) {std::cerr << "Error loading edge data: " << e.what() << '\n';
exit(1);
}
}
}

} // namespace  souffle

namespace  souffle {
using namespace souffle;
class Stratum_parkinson_disease_set_2768b32e307d7257 {
public:
 Stratum_parkinson_disease_set_2768b32e307d7257(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_i__0__1::Type& rel_parkinson_disease_set_de5887c01e2b44b1);
void run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret);
private:
SymbolTable& symTable;
RecordTable& recordTable;
ConcurrentCache<std::string,std::regex>& regexCache;
bool& pruneImdtRels;
bool& performIO;
SignalHandler*& signalHandler;
std::atomic<std::size_t>& iter;
std::atomic<RamDomain>& ctr;
std::string& inputDirectory;
std::string& outputDirectory;
t_btree_i__0__1::Type* rel_parkinson_disease_set_de5887c01e2b44b1;
};
} // namespace  souffle
namespace  souffle {
using namespace souffle;
 Stratum_parkinson_disease_set_2768b32e307d7257::Stratum_parkinson_disease_set_2768b32e307d7257(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_i__0__1::Type& rel_parkinson_disease_set_de5887c01e2b44b1):
symTable(symTable),
recordTable(recordTable),
regexCache(regexCache),
pruneImdtRels(pruneImdtRels),
performIO(performIO),
signalHandler(signalHandler),
iter(iter),
ctr(ctr),
inputDirectory(inputDirectory),
outputDirectory(outputDirectory),
rel_parkinson_disease_set_de5887c01e2b44b1(&rel_parkinson_disease_set_de5887c01e2b44b1){
}

void Stratum_parkinson_disease_set_2768b32e307d7257::run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret){
signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C0030567").
in file test.dl [5:1-5:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(0))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:D010300").
in file test.dl [6:1-6:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(1))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("OMIM:MTHU074205").
in file test.dl [7:1-7:42])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(2))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MONDO:0005180").
in file test.dl [8:1-8:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(3))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("KEGG:05012").
in file test.dl [9:1-9:37])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(4))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C2931436").
in file test.dl [10:1-10:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(5))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C537176").
in file test.dl [11:1-11:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(6))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C3501657").
in file test.dl [12:1-12:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(7))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C566017").
in file test.dl [13:1-13:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(8))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C3501658").
in file test.dl [14:1-14:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(9))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C564631").
in file test.dl [15:1-15:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(10))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C3496588").
in file test.dl [16:1-16:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(11))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C565204").
in file test.dl [17:1-17:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(12))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C1847360").
in file test.dl [18:1-18:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(13))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C564653").
in file test.dl [19:1-19:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(14))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C564345").
in file test.dl [20:1-20:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(15))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C1845165").
in file test.dl [21:1-21:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(16))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C564486").
in file test.dl [22:1-22:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(17))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MESH:C567726").
in file test.dl [23:1-23:39])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(18))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C3280133").
in file test.dl [24:1-24:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(19))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C3280271").
in file test.dl [25:1-25:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(20))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C4016848").
in file test.dl [26:1-26:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(21))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("UMLS:C4225353").
in file test.dl [27:1-27:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(22))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MONDO:0014604").
in file test.dl [28:1-28:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(23))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();signalHandler->setMsg(R"_(parkinson_disease_set("MONDO:0010360").
in file test.dl [29:1-29:40])_");
[&](){
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
Tuple<RamDomain,1> tuple{{ramBitCast(RamSigned(24))}};
rel_parkinson_disease_set_de5887c01e2b44b1->insert(tuple,READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt));
}
();}

} // namespace  souffle

namespace  souffle {
using namespace souffle;
class Stratum_result_0801b368bb1687d4 {
public:
 Stratum_result_0801b368bb1687d4(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_iiii__1_3_0_2__1111__0101::Type& rel_edge_04d25f5060e9043b,t_btree_i__0__1::Type& rel_parkinson_disease_set_de5887c01e2b44b1,t_btree_i__0__1::Type& rel_result_8d266e5660001a15);
void run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret);
private:
SymbolTable& symTable;
RecordTable& recordTable;
ConcurrentCache<std::string,std::regex>& regexCache;
bool& pruneImdtRels;
bool& performIO;
SignalHandler*& signalHandler;
std::atomic<std::size_t>& iter;
std::atomic<RamDomain>& ctr;
std::string& inputDirectory;
std::string& outputDirectory;
t_btree_iiii__1_3_0_2__1111__0101::Type* rel_edge_04d25f5060e9043b;
t_btree_i__0__1::Type* rel_parkinson_disease_set_de5887c01e2b44b1;
t_btree_i__0__1::Type* rel_result_8d266e5660001a15;
};
} // namespace  souffle
namespace  souffle {
using namespace souffle;
 Stratum_result_0801b368bb1687d4::Stratum_result_0801b368bb1687d4(SymbolTable& symTable,RecordTable& recordTable,ConcurrentCache<std::string,std::regex>& regexCache,bool& pruneImdtRels,bool& performIO,SignalHandler*& signalHandler,std::atomic<std::size_t>& iter,std::atomic<RamDomain>& ctr,std::string& inputDirectory,std::string& outputDirectory,t_btree_iiii__1_3_0_2__1111__0101::Type& rel_edge_04d25f5060e9043b,t_btree_i__0__1::Type& rel_parkinson_disease_set_de5887c01e2b44b1,t_btree_i__0__1::Type& rel_result_8d266e5660001a15):
symTable(symTable),
recordTable(recordTable),
regexCache(regexCache),
pruneImdtRels(pruneImdtRels),
performIO(performIO),
signalHandler(signalHandler),
iter(iter),
ctr(ctr),
inputDirectory(inputDirectory),
outputDirectory(outputDirectory),
rel_edge_04d25f5060e9043b(&rel_edge_04d25f5060e9043b),
rel_parkinson_disease_set_de5887c01e2b44b1(&rel_parkinson_disease_set_de5887c01e2b44b1),
rel_result_8d266e5660001a15(&rel_result_8d266e5660001a15){
}

void Stratum_result_0801b368bb1687d4::run([[maybe_unused]] const std::vector<RamDomain>& args,[[maybe_unused]] std::vector<RamDomain>& ret){
signalHandler->setMsg(R"_(result(drug) :- 
   edge(drug,"biolink:treats",disease,"False"),
   parkinson_disease_set(disease).
in file test.dl [32:1-32:96])_");
if(!(rel_edge_04d25f5060e9043b->empty()) && !(rel_parkinson_disease_set_de5887c01e2b44b1->empty())) {
[&](){
CREATE_OP_CONTEXT(rel_edge_04d25f5060e9043b_op_ctxt,rel_edge_04d25f5060e9043b->createContext());
CREATE_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt,rel_parkinson_disease_set_de5887c01e2b44b1->createContext());
CREATE_OP_CONTEXT(rel_result_8d266e5660001a15_op_ctxt,rel_result_8d266e5660001a15->createContext());
auto range = rel_edge_04d25f5060e9043b->lowerUpperRange_0101(Tuple<RamDomain,4>{{ramBitCast<RamDomain>(MIN_RAM_SIGNED), ramBitCast(RamSigned(25)), ramBitCast<RamDomain>(MIN_RAM_SIGNED), ramBitCast(RamSigned(26))}},Tuple<RamDomain,4>{{ramBitCast<RamDomain>(MAX_RAM_SIGNED), ramBitCast(RamSigned(25)), ramBitCast<RamDomain>(MAX_RAM_SIGNED), ramBitCast(RamSigned(26))}},READ_OP_CONTEXT(rel_edge_04d25f5060e9043b_op_ctxt));
for(const auto& env0 : range) {
if( rel_parkinson_disease_set_de5887c01e2b44b1->contains(Tuple<RamDomain,1>{{ramBitCast(env0[2])}},READ_OP_CONTEXT(rel_parkinson_disease_set_de5887c01e2b44b1_op_ctxt))) {
Tuple<RamDomain,1> tuple{{ramBitCast(env0[0])}};
rel_result_8d266e5660001a15->insert(tuple,READ_OP_CONTEXT(rel_result_8d266e5660001a15_op_ctxt));
}
}
}
();}
if (performIO) {
try {std::map<std::string, std::string> directiveMap({{"IO","file"},{"attributeNames","drug"},{"auxArity","0"},{"name","result"},{"operation","output"},{"output-dir","."},{"params","{\"records\": {}, \"relation\": {\"arity\": 1, \"params\": [\"drug\"]}}"},{"types","{\"ADTs\": {}, \"records\": {}, \"relation\": {\"arity\": 1, \"types\": [\"s:symbol\"]}}"}});
if (outputDirectory == "-"){directiveMap["IO"] = "stdout"; directiveMap["headers"] = "true";}
else if (!outputDirectory.empty()) {directiveMap["output-dir"] = outputDirectory;}
IOSystem::getInstance().getWriter(directiveMap, symTable, recordTable)->writeAll(*rel_result_8d266e5660001a15);
} catch (std::exception& e) {std::cerr << e.what();exit(1);}
}
if (pruneImdtRels) rel_edge_04d25f5060e9043b->purge();
if (pruneImdtRels) rel_parkinson_disease_set_de5887c01e2b44b1->purge();
}

} // namespace  souffle

namespace  souffle {
using namespace souffle;
class Sf_test: public SouffleProgram {
public:
 Sf_test();
 ~Sf_test();
void run();
void runAll(std::string inputDirectoryArg = "",std::string outputDirectoryArg = "",bool performIOArg = true,bool pruneImdtRelsArg = true);
void printAll([[maybe_unused]] std::string outputDirectoryArg = "");
void loadAll([[maybe_unused]] std::string inputDirectoryArg = "");
void dumpInputs();
void dumpOutputs();
SymbolTable& getSymbolTable();
RecordTable& getRecordTable();
void setNumThreads(std::size_t numThreadsValue);
void executeSubroutine(std::string name,const std::vector<RamDomain>& args,std::vector<RamDomain>& ret);
private:
void runFunction(std::string inputDirectoryArg,std::string outputDirectoryArg,bool performIOArg,bool pruneImdtRelsArg);
SymbolTableImpl symTable;
SpecializedRecordTable<0> recordTable;
ConcurrentCache<std::string,std::regex> regexCache;
Own<t_btree_iiii__1_3_0_2__1111__0101::Type> rel_edge_04d25f5060e9043b;
souffle::RelationWrapper<t_btree_iiii__1_3_0_2__1111__0101::Type> wrapper_rel_edge_04d25f5060e9043b;
Own<t_btree_i__0__1::Type> rel_parkinson_disease_set_de5887c01e2b44b1;
souffle::RelationWrapper<t_btree_i__0__1::Type> wrapper_rel_parkinson_disease_set_de5887c01e2b44b1;
Own<t_btree_i__0__1::Type> rel_result_8d266e5660001a15;
souffle::RelationWrapper<t_btree_i__0__1::Type> wrapper_rel_result_8d266e5660001a15;
Stratum_edge_9543a759b165a2cb stratum_edge_31e40d0d94fe9f7c;
Stratum_parkinson_disease_set_2768b32e307d7257 stratum_parkinson_disease_set_341c57c7d15771c2;
Stratum_result_0801b368bb1687d4 stratum_result_a2a91f171fb8739c;
std::string inputDirectory;
std::string outputDirectory;
SignalHandler* signalHandler{SignalHandler::instance()};
std::atomic<RamDomain> ctr{};
std::atomic<std::size_t> iter{};
};
} // namespace  souffle
namespace  souffle {
using namespace souffle;
 Sf_test::Sf_test():
symTable({
	R"_(UMLS:C0030567)_",
	R"_(MESH:D010300)_",
	R"_(OMIM:MTHU074205)_",
	R"_(MONDO:0005180)_",
	R"_(KEGG:05012)_",
	R"_(UMLS:C2931436)_",
	R"_(MESH:C537176)_",
	R"_(UMLS:C3501657)_",
	R"_(MESH:C566017)_",
	R"_(UMLS:C3501658)_",
	R"_(MESH:C564631)_",
	R"_(UMLS:C3496588)_",
	R"_(MESH:C565204)_",
	R"_(UMLS:C1847360)_",
	R"_(MESH:C564653)_",
	R"_(MESH:C564345)_",
	R"_(UMLS:C1845165)_",
	R"_(MESH:C564486)_",
	R"_(MESH:C567726)_",
	R"_(UMLS:C3280133)_",
	R"_(UMLS:C3280271)_",
	R"_(UMLS:C4016848)_",
	R"_(UMLS:C4225353)_",
	R"_(MONDO:0014604)_",
	R"_(MONDO:0010360)_",
	R"_(biolink:treats)_",
	R"_(False)_",
}),
recordTable(),
regexCache(),
rel_edge_04d25f5060e9043b(mk<t_btree_iiii__1_3_0_2__1111__0101::Type>()),
wrapper_rel_edge_04d25f5060e9043b(0, *rel_edge_04d25f5060e9043b, *this, "edge", std::array<const char *,4>{{"s:symbol","s:symbol","s:symbol","s:symbol"}}, std::array<const char *,4>{{"subj","pred","obj","neg"}}, 0),
rel_parkinson_disease_set_de5887c01e2b44b1(mk<t_btree_i__0__1::Type>()),
wrapper_rel_parkinson_disease_set_de5887c01e2b44b1(1, *rel_parkinson_disease_set_de5887c01e2b44b1, *this, "parkinson_disease_set", std::array<const char *,1>{{"s:symbol"}}, std::array<const char *,1>{{"x"}}, 0),
rel_result_8d266e5660001a15(mk<t_btree_i__0__1::Type>()),
wrapper_rel_result_8d266e5660001a15(2, *rel_result_8d266e5660001a15, *this, "result", std::array<const char *,1>{{"s:symbol"}}, std::array<const char *,1>{{"drug"}}, 0),
stratum_edge_31e40d0d94fe9f7c(symTable,recordTable,regexCache,pruneImdtRels,performIO,signalHandler,iter,ctr,inputDirectory,outputDirectory,*rel_edge_04d25f5060e9043b),
stratum_parkinson_disease_set_341c57c7d15771c2(symTable,recordTable,regexCache,pruneImdtRels,performIO,signalHandler,iter,ctr,inputDirectory,outputDirectory,*rel_parkinson_disease_set_de5887c01e2b44b1),
stratum_result_a2a91f171fb8739c(symTable,recordTable,regexCache,pruneImdtRels,performIO,signalHandler,iter,ctr,inputDirectory,outputDirectory,*rel_edge_04d25f5060e9043b,*rel_parkinson_disease_set_de5887c01e2b44b1,*rel_result_8d266e5660001a15){
addRelation("edge", wrapper_rel_edge_04d25f5060e9043b, true, false);
addRelation("parkinson_disease_set", wrapper_rel_parkinson_disease_set_de5887c01e2b44b1, false, false);
addRelation("result", wrapper_rel_result_8d266e5660001a15, false, true);
}

 Sf_test::~Sf_test(){
}

void Sf_test::runFunction(std::string inputDirectoryArg,std::string outputDirectoryArg,bool performIOArg,bool pruneImdtRelsArg){

    this->inputDirectory  = std::move(inputDirectoryArg);
    this->outputDirectory = std::move(outputDirectoryArg);
    this->performIO       = performIOArg;
    this->pruneImdtRels   = pruneImdtRelsArg;

    // set default threads (in embedded mode)
    // if this is not set, and omp is used, the default omp setting of number of cores is used.
#if defined(_OPENMP)
    if (0 < getNumThreads()) { omp_set_num_threads(static_cast<int>(getNumThreads())); }
#endif

    signalHandler->set();
// -- query evaluation --
{
 auto t0 = std::chrono::steady_clock::now();
 std::vector<RamDomain> args, ret;
stratum_edge_31e40d0d94fe9f7c.run(args, ret);
 auto t1 = std::chrono::steady_clock::now();
 std::cerr << "[stratum:edge] wall=" << std::chrono::duration<double>(t1 - t0).count()
           << "s size=" << rel_edge_04d25f5060e9043b->size() << std::endl;
}
{
 auto t0 = std::chrono::steady_clock::now();
 std::vector<RamDomain> args, ret;
stratum_parkinson_disease_set_341c57c7d15771c2.run(args, ret);
 auto t1 = std::chrono::steady_clock::now();
 std::cerr << "[stratum:parkinson_disease_set] wall=" << std::chrono::duration<double>(t1 - t0).count()
           << "s size=" << rel_parkinson_disease_set_de5887c01e2b44b1->size() << std::endl;
}
{
 auto t0 = std::chrono::steady_clock::now();
 std::vector<RamDomain> args, ret;
stratum_result_a2a91f171fb8739c.run(args, ret);
 auto t1 = std::chrono::steady_clock::now();
 std::cerr << "[stratum:result] wall=" << std::chrono::duration<double>(t1 - t0).count()
           << "s size=" << rel_result_8d266e5660001a15->size() << std::endl;
}

// -- relation hint statistics --
signalHandler->reset();
}

void Sf_test::run(){
runFunction("", "", false, false);
}

void Sf_test::runAll(std::string inputDirectoryArg,std::string outputDirectoryArg,bool performIOArg,bool pruneImdtRelsArg){
runFunction(inputDirectoryArg, outputDirectoryArg, performIOArg, pruneImdtRelsArg);
}

void Sf_test::printAll([[maybe_unused]] std::string outputDirectoryArg){
try {std::map<std::string, std::string> directiveMap({{"IO","file"},{"attributeNames","drug"},{"auxArity","0"},{"name","result"},{"operation","output"},{"output-dir","."},{"params","{\"records\": {}, \"relation\": {\"arity\": 1, \"params\": [\"drug\"]}}"},{"types","{\"ADTs\": {}, \"records\": {}, \"relation\": {\"arity\": 1, \"types\": [\"s:symbol\"]}}"}});
if (!outputDirectoryArg.empty()) {directiveMap["output-dir"] = outputDirectoryArg;}
IOSystem::getInstance().getWriter(directiveMap, symTable, recordTable)->writeAll(*rel_result_8d266e5660001a15);
} catch (std::exception& e) {std::cerr << e.what();exit(1);}
}

void Sf_test::loadAll([[maybe_unused]] std::string inputDirectoryArg){
try {std::map<std::string, std::string> directiveMap({{"IO","file"},{"attributeNames","subj\tpred\tobj\tneg"},{"auxArity","0"},{"columns","16:0:17:3"},{"fact-dir","."},{"filename","rtx-kg2_edges_2.8.1.tsv"},{"name","edge"},{"operation","input"},{"params","{\"records\": {}, \"relation\": {\"arity\": 4, \"params\": [\"subj\", \"pred\", \"obj\", \"neg\"]}}"},{"types","{\"ADTs\": {}, \"records\": {}, \"relation\": {\"arity\": 4, \"types\": [\"s:symbol\", \"s:symbol\", \"s:symbol\", \"s:symbol\"]}}"}});
if (!inputDirectoryArg.empty()) {directiveMap["fact-dir"] = inputDirectoryArg;}
IOSystem::getInstance().getReader(directiveMap, symTable, recordTable)->readAll(*rel_edge_04d25f5060e9043b);
} catch (std::exception& e) {std::cerr << "Error loading edge data: " << e.what() << '\n';
exit(1);
}
}

void Sf_test::dumpInputs(){
try {std::map<std::string, std::string> rwOperation;
rwOperation["IO"] = "stdout";
rwOperation["name"] = "edge";
rwOperation["types"] = "{\"relation\": {\"arity\": 4, \"auxArity\": 0, \"types\": [\"s:symbol\", \"s:symbol\", \"s:symbol\", \"s:symbol\"]}}";
IOSystem::getInstance().getWriter(rwOperation, symTable, recordTable)->writeAll(*rel_edge_04d25f5060e9043b);
} catch (std::exception& e) {std::cerr << e.what();exit(1);}
}

void Sf_test::dumpOutputs(){
try {std::map<std::string, std::string> rwOperation;
rwOperation["IO"] = "stdout";
rwOperation["name"] = "result";
rwOperation["types"] = "{\"relation\": {\"arity\": 1, \"auxArity\": 0, \"types\": [\"s:symbol\"]}}";
IOSystem::getInstance().getWriter(rwOperation, symTable, recordTable)->writeAll(*rel_result_8d266e5660001a15);
} catch (std::exception& e) {std::cerr << e.what();exit(1);}
}

SymbolTable& Sf_test::getSymbolTable(){
return symTable;
}

RecordTable& Sf_test::getRecordTable(){
return recordTable;
}

void Sf_test::setNumThreads(std::size_t numThreadsValue){
SouffleProgram::setNumThreads(numThreadsValue);
symTable.setNumLanes(getNumThreads());
recordTable.setNumLanes(getNumThreads());
regexCache.setNumLanes(getNumThreads());
}

void Sf_test::executeSubroutine(std::string name,const std::vector<RamDomain>& args,std::vector<RamDomain>& ret){
if (name == "edge") {
stratum_edge_31e40d0d94fe9f7c.run(args, ret);
return;}
if (name == "parkinson_disease_set") {
stratum_parkinson_disease_set_341c57c7d15771c2.run(args, ret);
return;}
if (name == "result") {
stratum_result_a2a91f171fb8739c.run(args, ret);
return;}
fatal(("unknown subroutine " + name).c_str());
}

} // namespace  souffle
namespace souffle {
SouffleProgram *newInstance_test(){return new  souffle::Sf_test;}
SymbolTable *getST_test(SouffleProgram *p){return &reinterpret_cast<souffle::Sf_test*>(p)->getSymbolTable();}
} // namespace souffle

#ifndef __EMBEDDED_SOUFFLE__
#include "souffle/CompiledOptions.h"
int main(int argc, char** argv)
{
try{
souffle::CmdOptions opt(R"(test.dl)",
R"()",
R"()",
false,
R"()",
1);
if (!opt.parse(argc,argv)) return 1;
souffle::Sf_test obj;
#if defined(_OPENMP) 
obj.setNumThreads(opt.getNumJobs());

#endif
obj.runAll(opt.getInputFileDir(), opt.getOutputFileDir());
return 0;
} catch(std::exception &e) { souffle::SignalHandler::instance()->error(e.what());}
}
#endif

namespace  souffle {
using namespace souffle;
class factory_Sf_test: souffle::ProgramFactory {
public:
souffle::SouffleProgram* newInstance();
 factory_Sf_test();
private:
};
} // namespace  souffle
namespace  souffle {
using namespace souffle;
souffle::SouffleProgram* factory_Sf_test::newInstance(){
return new  souffle::Sf_test();
}

 factory_Sf_test::factory_Sf_test():
souffle::ProgramFactory("test"){
}

} // namespace  souffle
namespace souffle {

#ifdef __EMBEDDED_SOUFFLE__
extern "C" {
souffle::factory_Sf_test __factory_Sf_test_instance;
}
#endif
} // namespace souffle

