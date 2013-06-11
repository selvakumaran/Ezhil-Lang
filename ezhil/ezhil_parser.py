#!/usr/bin/python
##
## (C) 2007, 2008 Muthiah Annamalai,
## Licensed under GPL Version 3
## 
## parser & AST  use the parsing frontend and 
## AST elements to build the parse tree.
## Class Parser
##
## ezhil parser & AST builder
## use the parsing frontend and similar
## AST elements from the previous classes
## TODO: extract scanner and AST members into a module for sharing.
## and use them here.

from math import *
import copy
import os, sys, string, inspect

## scanner for Ezhil language
from ezhil_scanner import EzhilToken
from ezhil_scanner import EzhilLex

## exceptions
from errors import RuntimeException, ParseException

## runtime elements
from runtime import  Environment, BuiltinFunction, \
 BlindBuiltins, DebugUtils

## AST elements
from ast import Expr, ExprCall, ExprList, Stmt, ReturnStmt, \
 BreakStmt, ContinueStmt, ElseStmt, IfStmt, WhileStmt, \
 ForStmt, AssignStmt, PrintStmt, EvalStmt, ArgList, \
 ValueList, Function, StmtList, Identifier, Number, \
 String

## use exprs language parser
from parser import Parser

## Parser implementes the grammar for 'exprs' language.
## Entry point is parse(), after appropriate ctor-setup.
class EzhilParser(Parser):
    """ when you add new language feature, add a AST class 
    and its evaluate methods. Also add a parser method """
    def __init__(self,lexer,fcn_map, builtin_map, dbg = False):
        if ( lexer.__class__ != EzhilLex ):
                raise RuntimeException("Cannot find Ezhil lexer class")
        Parser.__init__(self,lexer,fcn_map,builtin_map,dbg)


    def factory(lexer,fcn_map,builtin_map, dbg = False):
        """ Factory method """
        return EzhilParser(lexer,fcn_map,builtin_map, dbg)
    factory = staticmethod(factory)

    def match(self,kind):
        ## if match return token, else ParseException
        tok = self.dequeue()
        if ( tok.kind != kind ):
            raise ParseException("cannot find token "+ \
                                 EzhilToken.get_name(kind) + " got " \
                                + str(tok)  \
                                + " instead!")
        return tok

    def parse(self):
        """ parser routine """
        self.ast = StmtList()
        while ( not self.lex.end_of_tokens() ):
            self.dbg_msg( "AST length = %d"%len(self.ast) )
            if ( self.lex.peek().kind ==  EzhilToken.DEF ):
                self.dbg_msg ( "parsing for function" )
                ## save function in a global table.
                func = self.function()
                self.warn_function_overrides(func.name)
                self.function_map[func.name]=func
            else:
                self.dbg_msg( "parsing for stmt" )
                st = self.stmt()
                if ( not self.parsing_function ):
                    self.ast.append(st)
        return self.ast


    def stmtlist(self):
        """ parse a bunch of statements """
        self.dbg_msg(" STMTLIST ")
        stlist = StmtList()
        while( not self.lex.end_of_tokens() ):
            self.dbg_msg("STMTLIST => STMT")
            ptok = self.peek()
            if ( ptok.kind ==  EzhilToken.END ):
                self.dbg_msg("End token found");
                break
            if ( not self.inside_if and 
                 ( ptok.kind ==  EzhilToken.ELSE
                   or ptok.kind ==  EzhilToken.ELSEIF ) ):
                break
            st = self.stmt()
            stlist.append( st )
        return stlist
    
    def stmt(self):
        """ try an assign, print, return, if or eval statement """
        self.dbg_msg(" STMT ")
        ptok = self.peek()
        self.dbg_msg("stmt: peeking at "+str(ptok))
        if ( ptok.kind ==  EzhilToken.RETURN ):             
            ## return <expression>
            self.dbg_msg('enter->return: <expression>')
            ret_tok = self.dequeue()
            [l,c]=ret_tok.get_line_col();
            rstmt = ReturnStmt(self.expr(),l,c,self.debug)
            self.dbg_msg("return statement parsed")
            return rstmt
        elif ( ptok.kind ==  EzhilToken.PRINT ):
            ## print <expression>
            print_tok = self.dequeue()
            [l,c]=print_tok.get_line_col();
            return PrintStmt(self.exprlist(),l,c,self.debug)
        elif ( ptok.kind ==  EzhilToken.ELSE ):
            ## else stmtlist
            self.check_if_stack()
            ifstmt = self.if_stack.pop()
            self.dbg_msg("stmt-else: ")
            else_tok = self.dequeue()
            [l,c]=else_tok.get_line_col()
            body = self.stmtlist()
            else_stmt = ElseStmt( body , l, c, self.debug)
            ifstmt.set_next_stmt( else_stmt )
            return else_stmt
        elif ( ptok.kind ==  EzhilToken.ATRATEOF ):
            ## @ <expression> {if | while | elseif}
            at_tok = self.match(EzhilToken.ATRATEOF)
            exp = self.expr();
            ptok = self.peek();
            if ( ptok.kind == EzhilToken.IF ):
                ## @ <expression> if { stmtlist }
                if_tok = self.dequeue()
                [l,c]=if_tok.get_line_col();
                ifstmt = IfStmt( exp, None, None, l, c, self.debug)
                self.if_stack.append(ifstmt)
                body = self.stmtlist()
                ifstmt.set_body( body )
                ptok = self.peek()
                if ( ptok.kind in [ EzhilToken.ATRATEOF,  EzhilToken.ELSE] ):
                    self.inside_if = True
                    next_stmt = self.stmtlist()
                    self.inside_if = False
                    ifstmt.set_next_stmt( next_stmt )
                self.match( EzhilToken.END)
                return ifstmt
            elif ( ptok.kind ==  EzhilToken.ELSEIF ):
                ## @ <expression> elseif { stmtlist }
                elseif_tok = self.dequeue()
                [l,c]=elseif_tok.get_line_col();
                self.check_if_stack()
                elseif_stmt = IfStmt( exp, None, None, l, c, self.debug )
                ifstmt = self.if_stack[-1]
                ifstmt.set_next_stmt( elseif_stmt )
                self.if_stack.pop()
                self.if_stack.append( elseif_stmt )
                body = self.stmtlist( )
                elseif_stmt.set_body ( body )
                return elseif_stmt
            elif ( ptok.kind ==  EzhilToken.WHILE ):
                ## @ ( expr ) while { body } end
               self.loop_stack.append(True);
               self.dbg_msg("while-statement");
               while_tok = self.dequeue();
               [l,c]=while_tok.get_line_col()
               wexpr = exp;
               body = self.stmtlist( )
               self.match( EzhilToken.END)
               whilestmt = WhileStmt(wexpr, body, l, c, self.debug);
               self.loop_stack.pop();
               return whilestmt
        elif ( ptok.kind ==  EzhilToken.FOR ):
            ## Fixme : empty for loops not allowed.
            """ For ( exp1 , exp2 , exp3 ) stmtlist  end"""
            self.loop_stack.append(True)
            self.dbg_msg("for-statement")
            for_tok = self.dequeue()
            self.match( EzhilToken.LPAREN)

            lhs = self.expr()
            init = lhs 
            ptok = self.peek()
            if ( ptok.kind in  EzhilToken.ASSIGNOP ):
                assign_tok = self.dequeue()
                [l,c]=assign_tok.get_line_col();
                rhs = self.expr()
                init = AssignStmt( lhs, assign_tok, rhs, l, c, self.debug)

            self.match( EzhilToken.COMMA )

            cond = self.expr();
            self.match( EzhilToken.COMMA )

            lhs = self.expr()
            update = lhs 
            ptok = self.peek()
            if ( ptok.kind in  EzhilToken.ASSIGNOP ):
                assign_tok = self.dequeue()
                [l,c]=assign_tok.get_line_col()
                rhs = self.expr()
                update = AssignStmt( lhs, assign_tok, rhs, l, c, self.debug)

            
            self.match( EzhilToken.RPAREN);
            body = self.stmtlist( )
            self.match( EzhilToken.END)
            [l,c]= for_tok.get_line_col();
            forstmt = ForStmt(init, cond, update, body, l, c, self.debug);
            self.loop_stack.pop();
            return forstmt
        elif ( ptok.kind ==  EzhilToken.BREAK ):
            ## break, must be in loop-environment
            self.dbg_msg("break-statement");
            break_tok = self.dequeue();
            [l,c]=break_tok.get_line_col()
            self.check_loop_stack(); ##raises a parse error
            brkstmt = BreakStmt( l, c, self.debug);
            return brkstmt

        elif ( ptok.kind ==  EzhilToken.CONTINUE ):
            ## continue, must be in loop-environment
            self.dbg_msg("continue-statement");
            cont_tok = self.dequeue();
            [l,c]=cont_tok.get_line_col()
            self.check_loop_stack(); ##raises a parse error
            cntstmt = ContinueStmt( l, c, self.debug);
            return cntstmt

        else:
            ## lval := rval
            ptok = self.peek()
            [l,c] = ptok.get_line_col()
            lhs = self.expr()
            self.dbg_msg("parsing expr: "+str(lhs))
            ptok = self.peek()
            if ( ptok.kind in  EzhilToken.ASSIGNOP ):
                assign_tok = self.dequeue()
                rhs = self.expr()
                [l,c]=assign_tok.get_line_col()
                return AssignStmt( lhs, assign_tok, rhs, l, c, self.debug)
            return EvalStmt( lhs, l, c, self.debug )
        raise ParseException("parsing Statement, unkown operators" + str(ptok))
    
    def function(self):
        """ def[kw] fname[id] (arglist) {body} end[kw] """
        if ( self.parsing_function ):
            raise ParseException(" Nested functions not allowed! ")

        self.parsing_function = True
        def_tok = self.dequeue()
        if ( def_tok.kind !=  EzhilToken.DEF ):
            raise ParseException("unmatched 'def'  in function " +str(def_tok))
        
        id_tok = self.dequeue()
        if ( id_tok.kind !=  EzhilToken.ID ):
            raise ParseException("expected identifier in function"+str(id_tok))
        
        arglist = self.arglist()
        self.dbg_msg( "finished parsing arglist" )
        body = self.stmtlist()

        self.match(  EzhilToken.END )
        [l,c] = def_tok.get_line_col()
        fval = Function( id_tok.val, arglist, body, l, c, self.debug )
        self.parsing_function = False
        self.dbg_msg( "finished parsing function" ) 
        return fval

    def valuelist(self):
        """parse: ( expr_1 , expr_2, ... ) """
        valueList = list()
        self.dbg_msg("valuelist: ")
        lparen_tok = self.match(  EzhilToken.LPAREN )
        while ( self.peek().kind !=  EzhilToken.RPAREN ):
            val = self.expr()
            self.dbg_msg("valuelist-expr: "+str(val))
            valueList.append( val )
            ptok = self.peek()
            if  ( ptok.kind ==  EzhilToken.RPAREN ):
                break
            elif ( ptok.kind ==  EzhilToken.COMMA ):
                self.match(  EzhilToken.COMMA )
            else:
                raise ParseException(" function call argument list "+str(ptok))
        self.match(  EzhilToken.RPAREN )
        [l,c] = lparen_tok.get_line_col()
        return ValueList(valueList, l, c, self.debug )


    def arglist(self):
        """parse: ( arg_1, arg_2, ... ) """
        self.dbg_msg( " ARGLIST " )
        args = list()
        lparen_tok = self.match(  EzhilToken.LPAREN )
        while ( self.peek().kind !=  EzhilToken.RPAREN ):
            arg_name = self.dequeue()
            args.append( arg_name.val )
            ptok = self.peek()
            if  ( ptok.kind ==  EzhilToken.RPAREN ):
                break
            elif ( ptok.kind ==  EzhilToken.COMMA ):
                self.match(  EzhilToken.COMMA )
            else:
                raise ParseException(" function definition argument list "
                                     +str(ptok))
        self.match(  EzhilToken.RPAREN )
        [l,c] = lparen_tok.get_line_col()
        return ArgList(args , l, c, self.debug )
        
    def exprlist(self):
        """   EXPRLIST : EXPR, EXPRLIST        
        ##  EXPRLIST : EXPR """
        self.dbg_msg( " EXPRLIST " )
        exprs=[]
        comma_tok = None
        l = 0; c = 0
        while ( not self.lex.end_of_tokens() ):
            exprs.append(self.expr())
            if self.lex.peek().kind !=  EzhilToken.COMMA:
                break            
            tok = self.match( EzhilToken.COMMA)
            if ( not comma_tok ):
                comma_tok = tok 

        if ( comma_tok ):
            [l,c] = comma_tok.get_line_col()
        self.dbg_msg("finished expression list")
        return ExprList(exprs, l, c, self.debug)


    def expr(self):
        self.dbg_msg( " EXPR " )
        val1=self.term()
        res=val1
        ptok = self.peek()
        if ptok.kind in  EzhilToken.ADDSUB:
            binop=self.dequeue()
            val2=self.expr()
            [l,c] = binop.get_line_col()
            res=Expr(val1,binop,val2, l, c, self.debug )
        elif ptok.kind ==  EzhilToken.LPAREN:
            ## function call -OR- array type.
            if ( res.__class__ != Identifier ):
                raise ParseException("invalid function call"+str(ptok))
            [l,c] = ptok.get_line_col()
            vallist = self.valuelist()
            res=ExprCall( res, vallist, l, c, self.debug )
        return res

    def term(self):
        """ this is a grammar abstraction; 
        but AST only has Expr elements"""
        self.dbg_msg( "term" )
        val1=self.factor()
        res=val1

        tok = self.peek()
        if ( tok.kind in  EzhilToken.MULDIV 
             or  tok.kind in  EzhilToken.COMPARE 
             or tok.kind in  EzhilToken.EXPMOD  ):
            binop=self.dequeue()
            val2=self.expr()
            [l,c] = binop.get_line_col()
            res=Expr(val1,binop,val2, l, c, self.debug)

        return res
    
    def factor(self):
        self.dbg_msg( "factor" )
        tok=self.peek()
        if tok.kind ==  EzhilToken.LPAREN:
            lparen_tok = self.dequeue()
            val=self.expr()
            if self.dequeue().kind!= EzhilToken.RPAREN:
                raise SyntaxError("Missing Parens")
        elif tok.kind ==  EzhilToken.NUMBER:
            tok_num = self.dequeue()
            [l, c] = tok_num.get_line_col()
            val = Number( tok.val , l, c, self.debug )
        elif tok.kind ==  EzhilToken.ID:
            tok_id = self.dequeue()
            [l, c] = tok_id.get_line_col()
            val = Identifier( tok.val , l, c, self.debug )
            ptok = self.peek()
            self.dbg_msg("factor: "+str(ptok) + " / "+str(tok) )
            if ( ptok.kind ==  EzhilToken.LPAREN ):
                ## function call
                [l, c] = ptok.get_line_col()
                vallist = self.valuelist()
                val=ExprCall( val, vallist, l, c, self.debug )
            elif ( ptok.kind ==  EzhilToken.LSQRBRACE ):
                ## array type
                val=None
                raise ParseException("arrays not implemented"+str(ptok));
        elif tok.kind ==  EzhilToken.STRING :
            str_tok = self.dequeue()
            [l,c] = str_tok.get_line_col()
            val = String( tok.val , l, c, self.debug )
        else:
            raise ParseException("Expected Number, found something "+str(tok))
        
        self.dbg_msg( "factor-returning: "+str(val) )
        return val

